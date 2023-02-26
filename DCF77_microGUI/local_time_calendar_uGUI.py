import uasyncio
import ustruct, utime, machine
from machine import Timer

import micropython
micropython.alloc_emergency_exception_buf(100)

class LocalTimeCalendar():
    """
    """
    def __init__(self):
        #init conversion tables
#         self._month_values = ("JAN","FEV","MAR","AVR","MAI","JUN","JUL","AOU","SEP","OCT","NOV","DEC")
#         self._week_day_values = ("LUN","MAR","MER","JEU","VEN","SAM","DIM")
        self._time_zone_values = (0,2,1) #time_zone_code = 2 => CET => UTC+1, time_zone_code = 1 => CEST => UTC+2
        
        #init local time        
        self.year = 2000
#         self.month = "xxx" # in (JAN ...DEC)
        self.month_num = 1 # in (1 ... 12)
        self.mday = 1 # in (1 ... 31)
        self.hour = 0 # in (0 ... 23)
        self.minute = 0 # in (0 ... 59)
        self.second = 0 # in (0 ... 59)
#         self.weekday = "xxx" # in (LUN ... DIM)
        self.weekday_num = 1 # in (1 ... 7)
        self.time_zone = 0 # UTC +{self.time_zone}
 
#     def get_local_time(self):
#      # localtime : t[0]:year, t[1]:month, t[2]:mday, t[3]:hour, t[4]:minute, t[5]:second, t[6]:weekday, t[7]:time_zone
#         clock_update = (self.year, self.month, self.mday, self.hour, self.minute, self.second, self.weekday, self.time_zone)
#         return clock_update
    def get_raw_time_and_date(self):
     # raw_time_and_date : t[0]:year, t[1]:month, t[2]:mday, t[3]:hour, t[4]:minute, t[5]:second, t[6]:weekday, t[7]:time_zone
        clock_update = (self.year, self.month_num, self.mday, self.hour, self.minute, self.second, self.weekday_num, self.time_zone)
        return clock_update

    def sync_time(self, DCF_time_pack):
        """
        When a DCF full correct frame is received, the decoder packs a set of bytes
        and this set is used to sync the local clock
        received pask : year, month_num, day, week_day_num, hours, minutes, time_zone_num
        """
        (year, month, day, week_day, hours, minutes, time_zone_code) = ustruct.unpack("6HB",DCF_time_pack)
        self.year = 2000+year
#         self.month = self._month_values[month-1]
        self.month_num = month
        self.mday = day
#         self.weekday = self._week_day_values[week_day-1]
        self.week_day_num = week_day
        self.hour = hours
        self.minute = minutes
        self.second = 0
        self.time_zone = self._time_zone_values[time_zone_code]

    def _next_hour(self):
        if self.hour==23:
            self.hour = 0
        else:
            self.hour +=1
            
    def _next_minute(self):
        if self.minute==59:
            self.minute = 0
            self._next_hour()
        else:
            self.minute +=1
            
    def next_second(self):
        # update time
        if self.second == 59:
            self.second = 0
            self._next_minute()
        else:
            self.second +=1
                
                
                
                
###############################################################################                
if __name__ == "__main__":
    print("test")
    from random import randint
    from debug_utility.pulses import *
# D0 = Probe(27) time_trigger
# D1 = Probe(16) -
# D2 = Probe(17) DCF_Decoder_stub.frame_decoder
# D3 = Probe(18) -
# D4 = Probe(19) -
# D5 = Probe(20) DCF_Display_stub.display_date_and_time
# D6 = Probe(21) DCF_Decoder_stub._end_of_frame
# D7 = Probe(26) -


######################### stub 
    class DCF_Display_stub():
        def __init__(self):
            print("init DCF_Display_stub")
            self._month_values = ("JAN","FEV","MAR","AVR","MAI","JUN","JUL","AOU","SEP","OCT","NOV","DEC")
            self._week_day_values = ("LUN","MAR","MER","JEU","VEN","SAM","DIM")
                
        def display_date_and_time(self, clock_update):
            LOCAL_TIME_TAB = const("\t\t\t")
            D5.on()
            # raw_time_and_date : t[0]:year, t[1]:month, t[2]:mday, t[3]:hour, t[4]:minute, t[5]:second, t[6]:weekday, t[7]:time_zone
            year, month_num, mday, hour, minute, second, week_day_num, time_zone = clock_update
#             print(f"{LOCAL_TIME_TAB}LocalTime: {clock_update}")
            print(f"{LOCAL_TIME_TAB}LocalTime: {self._week_day_values[week_day_num-1]:3s} {mday:02d} {self._month_values[month_num-1]:3s} {year:4d} {hour:02d}:{minute:002d}:{second:02d} UTC{time_zone:+01d}")
            D5.off()

            
    class DCF_decoder_stub():
        def __init__(self,local_clock_calendar):
            print("init DCF_decoder_stub")
            self._local_time = local_clock_calendar
            self.time_zone_num = randint(1,2)
            self.minutes = randint(1,59)
            self.hours = randint(0,23)
            self.month = randint(1,12)
            self.day = randint(1,31)
            self.week_day_num = randint(1,7)
            self.year = randint(20,30)
             
        def _change_calendar(self):
            self.time_zone_num = randint(1,2)
            self.minutes = randint(1,59)
            self.hours = randint(0,23)
            self.day = randint(1,31)
            self.month = randint(1,12)
            self.week_day_num = randint(1,7)
            self.year = randint(20,30)
            
        async def frame_decoder(self):
            while True:
                D2.off()
                await uasyncio.sleep(randint(10,20))
                D2.on()
                print("Frame sync")
                self._change_calendar()
                self._local_time.sync_time(ustruct.pack("6HB",
                     self.year, self.month, self.day, self.week_day_num, self.hours, self.minutes, self.time_zone_num))
                
######################### test program     
    def timer_IRQ(timer):
        timer_elapsed.set()
        
    async def time_trigger():
        while True:
            D0.off()
            await timer_elapsed.wait()
            D0.on()
            timer_elapsed.clear()
            local_time.next_second()
            display.display_date_and_time(local_time.get_raw_time_and_date())

######################### triggering mechanism = 1-second internal timer
    timer = Timer(mode=Timer.PERIODIC, freq=1, callback=timer_IRQ)
    timer_elapsed = uasyncio.ThreadSafeFlag()
    
    local_time = LocalTimeCalendar()
    display = DCF_Display_stub()
    DCF_decoder = DCF_decoder_stub(local_time)

######################### start coroutines
    scheduler = uasyncio.get_event_loop()
    
    scheduler.create_task(time_trigger())
    scheduler.create_task(DCF_decoder.frame_decoder())
    
    scheduler.run_forever()
