import uasyncio, ustruct, utime
from lib_pico.filter import PID, FilteredPID, clamp

import micropython
micropython.alloc_emergency_exception_buf(100)

from debug_utility.pulses import Probe
D0 = Probe(26)
D1 = Probe(16)
D2 = Probe(17)
D3 = Probe(18)
D4 = Probe(19)
D5 = Probe(20)
D6 = Probe(21)
D7 = Probe(22)


class LocalTimeCalendar():
    """
The local clock/calendar, triggered by 1-second local timer.
The one-second period is adjusted by a PID servo_loop, in order to take into account the actual routine processing time.
    """
    def __init__(self, display):
        self._display = display
        # Trigerring mechanism = PID
        #     G proportional gain of the PID corrector
        #     Ti integration time constant of the PID corrector
        #     Td derivative time constant of the PID corrector
        #     Ts sampling time      
        self.pid=FilteredPID( Ts=1000, G=.55 , Ti=3000 , Td=10 , N=10) # values determined experimentally
                # variables for the PID corrector in next_second coroutine
        self._last_time = 0
        self._current_delay = 10

        #init conversion tables
        self._month_values = ["xxx","JAN","FEV","MAR","AVR","MAI","JUN","JUL","AOU","SEP","OCT","NOV","DEC"]
        self._week_day_values = ["xxx","LUN","MAR","MER","JEU","VEN","SAM","DIM"]
        self._time_zone_values = [0,2,1] #time_zone = 2 => CET = +1, time_zone = 1 => CEST = +2
        
        #init local time
        self.year = 0
        self.month = "xxx"
        self.day = 0
        self.week_day = "xxx"
        self.hours = 0
        self.minutes = 0
        self.seconds = 0
        self.time_zone = 0
        
        # init display
        clock_update = (self.week_day, self.day, self.month, self.year,
                       self.hours, self.minutes, self.seconds, self.time_zone)
        self._display.update_date_and_time(clock_update)

    def update_time(self, time_pack):
        """
        When a DCF frame is received, the decoder packs a set of bites
        and this set is used to update the local clock
        """
        D6.on()
        (year, month, day, week_day, hours, minutes, time_zone) = ustruct.unpack("6HB",time_pack)
        self.year = year
        self.month = self._month_values[month]
        self.day = day
        self.week_day = self._week_day_values[week_day]
        self.hours = hours
        self.minutes = minutes
        self.seconds = 0
        self.time_zone = self._time_zone_values[time_zone]
        clock_update = (self.week_day, self.day, self.month, self.year,
                       self.hours, self.minutes, self.seconds, self.time_zone)
        self._display.update_date_and_time(clock_update)
        D6.off()

    def start_new_minute(self):
        """ method used when a "next minute" signal is received """
        D5.on()
        self.minutes +=1
        self.seconds = 0
        clock_update = (self.week_day, self.day, self.month, self.year,
                       self.hours, self.minutes, self.seconds, self.time_zone)
        self._display.update_date_and_time(clock_update)
        D5.off()
        
    def _next_hour(self):
        if self.hours==23:
            self.hours = 0
        else:
            self.hours +=1
            
    def _next_minute(self):
        if self.minutes==59:
            self.minutes = 0
            self._next_hour()
        else:
            self.minutes +=1
            
    async def next_second(self):
        """ coroutine triggered by the 1-second local timer """
        while True:
            #triggering the coroutine
            delay = int(clamp(10, 1100, self._current_delay))
            D7.off()
            await uasyncio.sleep_ms(delay)
            D7.on()
                # measure the current period
            current_time = utime.ticks_ms()
            current_period = clamp(10, 1100, current_time - self._last_time) # we keep only the value between 900 and 1100 ms
            self._last_time = current_time
                # compute error between current_period and 1000 ms target for PID corrector
            D0.on()
            self._current_delay = self.pid.filter(1000 - current_period)
            D0.off()
                       
            # update time
            if self.seconds==59:
                self.seconds = 0
                self._next_minute()
                clock_update = (self.week_day, self.day, self.month, self.year,
                       self.hours, self.minutes, self.seconds, self.time_zone)
                self._display.update_date_and_time(clock_update)
            else:
                self.seconds +=1
                self._display.update_seconds(self.seconds)
            
            
if __name__ == "__main__":
    
    from random import randint
     
    SIGNAL_STATUS_TAB = const("")
    TIME_STATUS_TAB   = const("\t\t")
    LOCAL_TIME_TAB    = const("\t\t\t\t\t\t\t\t\t")

    class DCF_Display_stub():
        def __init__(self):
            print("init DCF_Display_stub")
            
        def update_time_status(self, event, new_status, message=""):
            print(f"{TIME_STATUS_TAB}time_status\t-- ({event:^20s}) --> [{new_status:^20s}] : {message}")
   
        def update_signal_status(self, current_string, event, new_status):
            if current_string != None:
                data = current_string[-1]
                rank = len(current_string)-1
                print(f"{SIGNAL_STATUS_TAB}signal_status\t-- ({event:^20s}) --> [{new_status:^20s}] : Data[{rank:0>2d}] = {data}")
            else:
                print(f"{SIGNAL_STATUS_TAB}signal_status\t-- ({event:^20s}) --> [{new_status:^20s}] : No Data")
                
        def update_date_and_time(self, clock_update):
            week_day , day, month, year, hours, minutes, seconds, time_zone = clock_update
            print(f"{LOCAL_TIME_TAB}LocalTime:\t{week_day} {day} {month} 20{year:0>2d}\t{hours:0>2d}:{minutes:0>2d}:{seconds:0>2d}\tgmt{time_zone:<+3d}")
        
        def update_seconds(self, seconds):
            print(f"{LOCAL_TIME_TAB}LocalTime:{seconds:0>2d}")
            
    class DCF_decoder_stub():
        def __init__(self,local_clock_calendar, display):
            print("init DCF_decoder_stub")
            self._local_time = local_clock_calendar
            self.display = display
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
                await uasyncio.sleep(randint(20,30))
                D2.on()
                print("Frame sync")
                self._change_calendar()
                self._local_time.update_time(ustruct.pack("6HB",
                     self.year, self.month, self.day, self.week_day_num, self.hours, self.minutes, self.time_zone_num))
        
        async def _end_of_frame(self):
            while True:
                await uasyncio.sleep(randint(15,25))
                print("EoF")
                self._local_time.start_new_minute()
                
 
            
    
    

    ################### test ############################ 
    # init main tasks
    display = DCF_Display_stub()
    local_clock_calendar = LocalTimeCalendar(display)
    DCF_decoder = DCF_decoder_stub(local_clock_calendar, display)

    # Local Time setup coroutines
    local_time_coroutine = local_clock_calendar.next_second()
    # DCF setup coroutines
    DCF_frame_coroutine = DCF_decoder.frame_decoder()    
    DCF_EoF_coroutine = DCF_decoder._end_of_frame()

    #start coroutines

    scheduler = uasyncio.get_event_loop()
    
    scheduler.create_task(local_time_coroutine)
    
    scheduler.create_task(DCF_frame_coroutine)
    scheduler.create_task(DCF_EoF_coroutine)
    
    scheduler.run_forever()
