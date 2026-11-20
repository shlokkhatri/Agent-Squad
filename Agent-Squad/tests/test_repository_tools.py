from app.tools.repository_tools import RepositoryStructureTool
from app.tools.file_tools import FileReadTool

def test_repository_tool():

    print("---Repository Tool Test---")

    # Test 1 = Repository structure

    structure_tool = RepositoryStructureTool()

    structure = structure_tool.run(
        repository_name = "sample_project"
    )

    print(f"Repository Structure : \n{structure}")

    # Test 2 = File reading

    reader_tool = FileReadTool()

    content = reader_tool.run(
        repository_name = "sample_project",
        file_path = "main.py"
    )

    print(f"\nFile Content :\n{content}")

    print("Repository Tools tested successfully ! ☻")

if __name__ == "__main__" :
    test_repository_tool()