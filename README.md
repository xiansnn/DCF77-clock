# DCF77
 A project that decodes radio signal from DCF77 station

The project uses lib_pico and debug_utility from https://github.com/xiansnn/RP2-micropython

In this version, the radio signal is received via a WebSDR (http://www.websdr.org/) and in particular the one from University of Twente in Enshede The Netherland (http://websdr.ewi.utwente.nl:8901/)
As a result, there is no direct reception of the radio siganl, but an audio signal extrated by the WebSDR, then an audio signal received by a microphone (HW-484 or KY-038)
