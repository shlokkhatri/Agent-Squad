from app.tools.file_write_tool import FileWriteTool

def test_file_write_tool():

    tool = FileWriteTool()

    print("--- File Write Tool Test ---")

    result = tool._run(
        repository_name = "sample_project",
        file_path = "test_output/hello.py",
        content = 'print("Hello from Agent Squad ! ♥")',
        overwrite = True
    )

    print(result)

    assert "successfully" in result.lower()

    print("\nFile Write Tool tested successfully!")


if __name__ == "__main__":

    test_file_write_tool()