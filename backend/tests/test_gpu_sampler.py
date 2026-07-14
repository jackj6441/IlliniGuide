from scripts.gpu_sampler import parse_nvidia_smi_output


def test_parse_nvidia_smi_csv_rows() -> None:
    text = (
        "0, 2026/07/14 10:00:00.000, 67, 4096, 141312\n"
        "1, 2026/07/14 10:00:00.000, 12, 1024, 141312\n"
    )

    samples = parse_nvidia_smi_output(
        text,
        sampled_at_utc="2026-07-14T10:00:00+00:00",
    )

    assert len(samples) == 2
    assert samples[0].gpu_index == 0
    assert samples[0].nvidia_timestamp == "2026/07/14 10:00:00.000"
    assert samples[0].utilization_gpu_percent == 67.0
    assert samples[0].memory_used_mib == 4096.0
    assert samples[0].memory_total_mib == 141312.0
    assert samples[0].sampled_at_utc == "2026-07-14T10:00:00+00:00"


def test_parse_nvidia_smi_skips_malformed_rows() -> None:
    text = (
        "index, timestamp, utilization.gpu, memory.used, memory.total\n"
        "0, 2026/07/14 10:00:00.000, 65, not-a-number, 141312\n"
        "1, 2026/07/14 10:00:00.000, 20, 1024, 141312\n"
    )

    samples = parse_nvidia_smi_output(text, sampled_at_utc="now")

    assert len(samples) == 1
    assert samples[0].gpu_index == 1
