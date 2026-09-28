from app.models.user_output import UserOutput
from app.schemas.A2A import WriterResponse


def test_repeated_citations_keep_the_same_number_across_sections(tmp_path):
    output = UserOutput(str(tmp_path), 1)
    for key in output.seq:
        output.set_res(key, WriterResponse(response_content="正文"))
    output.set_res(
        "eda",
        WriterResponse(response_content="甲{[^1]: Source A} 重复{[^1]: Source A}"),
    )
    output.set_res(
        "ques1",
        WriterResponse(response_content="复用{[^7]: Source A} 新文献{[^9]: Source B}"),
    )
    text = output.get_result_to_save()
    assert "复用[^1] 新文献[^2]" in text
    assert "[^1]: Source A" in text and "[^2]: Source B" in text
    assert "[^3]" not in text
    assert output.get_result_to_save() == text
