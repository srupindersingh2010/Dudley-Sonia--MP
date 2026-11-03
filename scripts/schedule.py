"""Choose the UTC cron that corresponds to 07:00 Europe/London that day."""
from datetime import datetime,time,timezone
from zoneinfo import ZoneInfo
import os

def should_run(event,schedule,now=None):
 if event!='schedule':return True
 local=(now or datetime.now(timezone.utc)).astimezone(ZoneInfo('Europe/London'))
 nominal=datetime.combine(local.date(),time(7),ZoneInfo('Europe/London')).astimezone(timezone.utc)
 return schedule==f'0 {nominal.hour} * * *'
if __name__=='__main__':
 result=should_run(os.environ.get('EVENT_NAME'),os.environ.get('EVENT_SCHEDULE'))
 print('run='+str(result).lower())
