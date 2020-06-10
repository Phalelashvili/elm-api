#!/usr/bin/env python3
import sys
import logging
from elm import ELM

logging.basicConfig(level=logging.DEBUG)
device = ELM(sys.argv[1], sys.argv[2])

device.setHeaderState(True)
device.allowLongMessages()

def recv(data):
    print('CALLBACK', data)

device.monitorAll(recv)

def c():
    device.execute('ATI', resumeMA=False)
def e(c):
    device.execute(c)

while True:
    try:
        print('eval:', eval(input()))
    except Exception as e:
        print('exception:', e)