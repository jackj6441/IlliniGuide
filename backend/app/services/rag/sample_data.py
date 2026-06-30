from dataclasses import dataclass


@dataclass(frozen=True)
class SampleChunk:
    course_id: str
    source_name: str
    source_url: str
    section_type: str
    chunk_text: str


SAMPLE_CHUNKS: tuple[SampleChunk, ...] = (
    SampleChunk(
        course_id="ECE 391",
        source_name="Mock Course Dataset",
        source_url="https://example.com/courses/ece-391",
        section_type="course_description",
        chunk_text=(
            "ECE 391 is a systems programming course focused on low-level programming, "
            "operating systems concepts, debugging, concurrency, and C programming."
        ),
    ),
    SampleChunk(
        course_id="ECE 385",
        source_name="Mock Course Dataset",
        source_url="https://example.com/courses/ece-385",
        section_type="course_description",
        chunk_text=(
            "ECE 385 covers digital systems, hardware design, SystemVerilog, FPGA labs, "
            "and computer engineering design foundations."
        ),
    ),
    SampleChunk(
        course_id="ECE 408",
        source_name="Mock Course Dataset",
        source_url="https://example.com/courses/ece-408",
        section_type="course_description",
        chunk_text=(
            "ECE 408 focuses on applied parallel programming, GPU programming, CUDA, "
            "performance optimization, and parallel algorithms."
        ),
    ),
    SampleChunk(
        course_id="CS 433",
        source_name="Mock Course Dataset",
        source_url="https://example.com/courses/cs-433",
        section_type="course_description",
        chunk_text=(
            "CS 433 studies computer system organization, architecture, memory hierarchy, "
            "instruction-level parallelism, and performance tradeoffs."
        ),
    ),
    SampleChunk(
        course_id="CS 444",
        source_name="Mock Course Dataset",
        source_url="https://example.com/courses/cs-444",
        section_type="course_description",
        chunk_text=(
            "CS 444 covers compiler construction, parsing, code generation, optimization, "
            "and language implementation."
        ),
    ),
)
