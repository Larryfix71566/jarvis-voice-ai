"""Two original diagnostic probes from the 63aaeef audit, reconstructed from the executed command.
These characterize old behavior; they are not pass/fail regression tests.
Run from a checkout: PYTHONPATH=. python /absolute/path/audit_python_probes.py
"""
import asyncio
import uuid
from jarvis.bot.ui_control import build_ui_control_tool
from jarvis.bot.console_protocol import validate_request

async def probe():
    sent=[]
    async def send(message): sent.append(message)
    _, handler=build_ui_control_tool(send)
    reply=await handler({'action':'display_popout'})
    print('Legacy tool probe:', {'sent':sent, 'reply':reply, 'native_ack_received':False})
asyncio.run(probe())
message={'type':'console/request','version':1,'session_id':str(uuid.uuid4()),'generation':str(uuid.uuid4()),'request_id':str(uuid.uuid4()),'revision':0,'action':'panel_detach','target':'result:'+str(uuid.uuid4()),'args':{'screen_id':'external-screen'}}
try:
    validate_request(message)
    print('Accepted panel_detach screen_id')
except ValueError as exc:
    print('Python detach-screen probe:', str(exc))
