# ====== Code Summary ======
# Behaviour of DeviceProbe: the first positive detector wins, a failing detector degrades to "no GPU"
# (a health probe never raises), the answer is memoized, and the default chain is torch-free.

# ====== Standard Library Imports ======
import sys

# ====== Third-Party Library Imports ======
from loggerplusplus.testing import capture

# ====== Internal Project Imports ======
from model_server_core import Device, DeviceProbe
from support.fakes.fake_cuda_detector import FakeCudaDetector


def test_a_positive_detector_reports_cuda() -> None:
    assert DeviceProbe([FakeCudaDetector(True)]).device() is Device.CUDA


def test_no_positive_detector_reports_cpu() -> None:
    probe = DeviceProbe([FakeCudaDetector(False), FakeCudaDetector(False)])

    assert probe.device() is Device.CPU
    assert probe.cuda_available() is False


def test_first_positive_detector_short_circuits_the_chain() -> None:
    first, second = FakeCudaDetector(True), FakeCudaDetector(True)

    DeviceProbe([first, second]).device()

    assert (first.calls, second.calls) == (1, 0)


def test_a_failing_detector_is_logged_and_the_chain_continues() -> None:
    with capture(level="WARNING") as logs:
        probe = DeviceProbe([FakeCudaDetector(fail=True), FakeCudaDetector(True)])
        device = probe.device()

    assert device is Device.CUDA
    assert "FakeCudaDetector failed" in logs
    assert "probe exploded" in logs


def test_every_detector_failing_degrades_to_cpu_without_raising() -> None:
    assert DeviceProbe([FakeCudaDetector(fail=True)]).device() is Device.CPU


def test_the_answer_is_memoized() -> None:
    detector = FakeCudaDetector(True)
    probe = DeviceProbe([detector])

    probe.device()
    probe.device()
    probe.cuda_available()

    assert detector.calls == 1


def test_device_values_are_the_cross_service_contract() -> None:
    assert (Device.CUDA.value, Device.CPU.value) == ("cuda", "cpu")


def test_default_probe_works_and_the_core_never_imports_an_ml_library() -> None:
    assert DeviceProbe().device() in {Device.CUDA, Device.CPU}
    assert not {"torch", "paddle", "transformers"} & set(sys.modules)
