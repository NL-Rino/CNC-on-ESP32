(PipeCut Studio - vi du G-code phang xuat tu CAM)
(X = doc phoi, Y = theo chu vi, don vi mm)
G21 G90
G0 X10 Y5
G1 X70 Y5 F1500
G2 X75 Y10 I0 J5
G1 X75 Y30
G2 X70 Y35 I-5 J0
G1 X10 Y35
G2 X5 Y30 I0 J-5
G1 X5 Y10
G2 X10 Y5 I5 J0
G0 X40 Y20
G3 X40 Y20 I-8 J0
G0 X0 Y0
M2
