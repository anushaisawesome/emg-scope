# TouchDesigner network builder — run INSIDE TouchDesigner's Textport:
#   exec(open('/Users/anusha/emg-scope/td_build.py').read())
#
# Builds in /project1: OSC In (port 9001, from bridge.py) driving a
# feedback-displacement flow with bloom. Clench = the field surges,
# brightens and spins; rest = slow drifting smoke.
#
# Start the bridge on the Mac FIRST so the OSC channel exists:
#   venv/bin/python bridge.py
#
# If this script prints WARN lines, paste them back to Claude — par
# names vary slightly between TD versions and each is fixable.

root = op('/project1')

# wipe previous build
for name in ['oscin1', 'noise_flow', 'noise_src', 'level_src', 'comp1',
             'feedback1', 'displace1', 'transform1', 'level_fade',
             'blur1', 'comp_bloom', 'null_out']:
    o = root.op(name)
    if o:
        o.destroy()


def P(o, candidates, value=None, expr=None):
    """Set the first matching parameter; warn if none exist."""
    for c in candidates:
        p = getattr(o.par, c, None)
        if p is not None:
            if expr is not None:
                p.expr = expr
            else:
                p.val = value
            return p
    print(f"WARN: {o.name}: none of {candidates} found")


E = "op('oscin1')['emg/effort']"   # effort expression, 0..1.5

# --- muscle input ------------------------------------------------------
osc = root.create(oscinCHOP, 'oscin1')
P(osc, ['port', 'netport'], 9001)

# --- displacement field ------------------------------------------------
flow = root.create(noiseTOP, 'noise_flow')
P(flow, ['resolutionw', 'resolution1'], 640)
P(flow, ['resolutionh', 'resolution2'], 360)
P(flow, ['mono'], True)
P(flow, ['period'], 2.5)
P(flow, ['tz'], expr="absTime.seconds*0.15")

# --- energy source: colour noise, opacity ∝ effort ---------------------
src = root.create(noiseTOP, 'noise_src')
P(src, ['resolutionw', 'resolution1'], 1280)
P(src, ['resolutionh', 'resolution2'], 720)
P(src, ['mono'], False)
P(src, ['period'], 0.6)
P(src, ['tz'], expr="absTime.seconds*0.4")
P(src, ['exponent'], 3)

lev_src = root.create(levelTOP, 'level_src')
P(lev_src, ['opacity'], expr=f"0.03 + 0.5*min(({E}),1)")

# --- feedback loop: feedback -> displace -> +source -> transform -> fade
fb = root.create(feedbackTOP, 'feedback1')
disp = root.create(displaceTOP, 'displace1')
comp = root.create(compositeTOP, 'comp1')
xform = root.create(transformTOP, 'transform1')
fade = root.create(levelTOP, 'level_fade')

P(comp, ['operand'], 'add')
P(disp, ['displaceweightx', 'displaceweightu', 'uvweight', 'weightx'],
  expr=f"0.005 + 0.05*min(({E}),1.2)")
P(disp, ['displaceweighty', 'displaceweightv', 'weighty'],
  expr=f"0.005 + 0.05*min(({E}),1.2)")
P(xform, ['sx', 'scalex'], expr=f"1.004 + 0.02*min(({E}),1)")
P(xform, ['sy', 'scaley'], expr=f"1.004 + 0.02*min(({E}),1)")
P(xform, ['rotate'], expr=f"0.15 + 3*min(({E}),1)")
P(fade, ['opacity'], 0.97)
P(fade, ['gamma1', 'gamma'], 0.98)

# wiring
src.outputConnectors[0].connect(lev_src.inputConnectors[0])
fb.outputConnectors[0].connect(disp.inputConnectors[0])
flow.outputConnectors[0].connect(disp.inputConnectors[1])
disp.outputConnectors[0].connect(comp.inputConnectors[0])
lev_src.outputConnectors[0].connect(comp.inputConnectors[1])
comp.outputConnectors[0].connect(xform.inputConnectors[0])
xform.outputConnectors[0].connect(fade.inputConnectors[0])
P(fb, ['top'], 'level_fade')

# --- bloom -------------------------------------------------------------
blur = root.create(blurTOP, 'blur1')
P(blur, ['size', 'filtersize'], expr=f"6 + 30*min(({E}),1)")
bloom = root.create(compositeTOP, 'comp_bloom')
P(bloom, ['operand'], 'add')

fade.outputConnectors[0].connect(blur.inputConnectors[0])
fade.outputConnectors[0].connect(bloom.inputConnectors[0])
blur.outputConnectors[0].connect(bloom.inputConnectors[1])

out = root.create(nullTOP, 'null_out')
bloom.outputConnectors[0].connect(out.inputConnectors[0])
out.viewer = True

# tidy layout
for i, o in enumerate([osc, flow, src, lev_src, fb, disp, comp, xform,
                       fade, blur, bloom, out]):
    o.nodeX = (i % 4) * 220
    o.nodeY = -(i // 4) * 160

print("Built. Right-click null_out viewer for fullscreen; bridge.py must be running for /emg/effort.")
