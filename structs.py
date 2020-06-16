from dataclasses import dataclass

@dataclass
class Protocols:
    AUTO = 0 # Automatic
    J1850_PWM  = 1 # SAE J1850 PWM (41.6 kbaud)
    J1850_VPW  = 2 # SAE J1850 VPW (10.4 kbaud)
    ISO9141_2  = 3 # ISO 9141-2 (5 baud init, 10.4 kbaud)
    ISO14230_4_SLOW = 4 # ISO 14230-4 KWP (5 baud init, 10.4 kbaud)
    ISO14230_4_FAST = 5 # ISO 14230-4 KWP (fast init, 10.4 kbaud)
    ISO15765_4_500KBPS = 6 # ISO 15765-4 CAN (11 bit ID, 500 kbaud)
    ISO15765_4_500KBPS_EXTENDED = 7 # ISO 15765-4 CAN (29 bit ID, 500 kbaud)
    ISO15765_4_250KBPS = 8 # ISO 15765-4 CAN (11 bit ID, 250 kbaud)
    ISO15765_4_250KBPS_EXTENDED = 9 # ISO 15765-4 CAN (29 bit ID, 250 kbaud)

    # same protocols but with more human names
    KLINE        = ISO9141_2
    KWP2000_SLOW = ISO14230_4_SLOW
    KWP2000_FAST = ISO14230_4_FAST
    CAN          = ISO15765_4_500KBPS_EXTENDED