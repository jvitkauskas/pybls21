# Coils
CL_POWER = 0
CL_TIMER = 1
CL_WEEK = 2
CL_Boost_MODE = 3
CL_BoostSWITCH_CTRL = 13
CL_RESET_FILTER_TIMER = 17
CL_RESET_ALARM = 18

# Holding registers
HR_MaxSPEED_MODE = 1
HR_SPEED_MODE = 2
HR_ManualSPEED = 17
HR_OPERATION_MODE = 43
HR_SetTEMP = 44
HR_TIMER_MODE = 49
HR_BPS_ROTOR_TYPE = 57
HR_BPS_ROTOR_MODE = 74
HR_SetBpsRotorMANUAL = 75

# Input registers
IR_CurTEMP_SuAirIn = 1
IR_CurTEMP_SuAirOut = 2
IR_CurTEMP_ExAirIn = 3  # Extract air from the rooms, at the unit inlet
IR_CurTEMP_ExAirOut = 4  # Exhaust air to the outside, at the unit outlet
IR_CurRH_Int = 10
IR_CurSuAirFLOW = 19  # Supply airflow, m³/h
IR_CurExAirFLOW = 20  # Extract airflow, m³/h
IR_CurSuPRESS = 21  # Supply duct pressure, Pa
IR_CurExPRESS = 22  # Extract duct pressure, Pa
IR_SuRPM = 23
IR_ExRPM = 24
IR_CurTIMER_TIME = 25  # High byte: minutes, low byte: seconds
IR_CurTIMER_TIME_HOURS = 26  # Low byte: hours
IR_CurFILTER_TIMER_HOURS_MINUTES = 27  # High byte: hours, low byte: minutes
IR_CurFILTER_TIMER_DAYS = 28
IR_TotalWorkingTime_HOURS_MINUTES = 29  # High byte: hours, low byte: minutes
IR_TotalWorkingTime_DAYS = 30
IR_StateFILTER = 31
IR_CurWeekSpeed = 32  # 0: standby, 1-5: scheduled speed
IR_VerMAIN_FMW_start = 34
IR_VerMAIN_FMW_end = 36
IR_DeviceTYPE = 37
IR_ALARM = 38
IR_BPS_ROTOR_U = 45
IR_StatusBpsRotor = 51
IR_CurSuFanSpeed = 52  # Actual supply fan performance, percent
IR_CurExFanSpeed = 53  # Actual extract fan performance, percent

# Discrete inputs: controller-reported heating/cooling activity
DI_StatusHEATER = 7
DI_StatusCOOLER = 8

# Discrete inputs: alarm codes 0 through 52
DI_ALARM_START = 19
DI_ALARM_COUNT = 53
