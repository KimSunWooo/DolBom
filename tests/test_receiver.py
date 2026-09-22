import time

from dolbom.tools.test_receiver import TestReceiver


def test_receiver_rebind_after_stop():
    rx = TestReceiver("127.0.0.1", 47801, 47802)
    rx.start()
    rx.stop()
    rx2 = TestReceiver("127.0.0.1", 47801, 47802)
    rx2.start()
    time.sleep(0.05)
    assert rx2._tcp_sock is not None
    assert rx2._udp_sock is not None
    rx2.stop()
