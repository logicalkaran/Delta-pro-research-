from probabilistic_validation_v2 import calibration_error

def test_calibration_error_zero(): assert calibration_error([0,1],[0,1])==0
