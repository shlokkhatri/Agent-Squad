from app.tools.file_delete_tool import FileDeleteTool
from app.tools.file_search_tool import FileSearchTool
from app.tools.file_write_tool import FileWriteTool
from app.tools.code_search_tool import CodeSearchTool


def test_file_search():

    print("\n--- FILE SEARCH TEST ---")

    tool = FileSearchTool()

    result = tool._run(
        repository_name="sample_project",
        search_query="main",
        extension=".py"
    )

    print(result)

    assert "main.py" in result

    print("► FILE SEARCH TOOL PASSED !")


def test_code_search():

    print("\n--- CODE SEARCH TEST ---")

    tool = CodeSearchTool()

    result = tool._run(
        repository_name="sample_project",
        search_query="greet_user"
    )

    print(result)

    assert "greet_user" in result

    print("► CODE SEARCH TOOL PASSED!")


def test_file_delete():

    print("\n--- FILE DELETE TEST ---")

    # Create the file first so this test does not depend on another test.
    FileWriteTool()._run(
        repository_name="sample_project",
        file_path="test_output/hello.py",
        content="print('delete me')",
        overwrite=True
    )

    tool = FileDeleteTool()

    result = tool._run(
        repository_name="sample_project",
        file_path="test_output/hello.py",
        confirm=True
    )

    print(result)

    assert "successfully" in result.lower()

    print("► FILE DELETE TOOL PASSED!")


if __name__ == "__main__":

    test_file_search()

    test_code_search()

    test_file_delete()

    print("\n► All File Management Tools tested successfully! ◄")