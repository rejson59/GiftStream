from app import desktop


def test_second_desktop_launch_cannot_acquire_instance_lock():
    desktop._release_single_instance()

    assert desktop._acquire_single_instance() is True
    assert desktop._acquire_single_instance() is False
    desktop._release_single_instance()
    assert desktop._acquire_single_instance() is True
    desktop._release_single_instance()
