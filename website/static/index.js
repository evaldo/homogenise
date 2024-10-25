  function deleteProject(project_id, project_name, project_description, type_operation) {
    alert(project_id)
    fetch("/maintainProject", {
    method: "POST",
    body: JSON.stringify({ project_id: project_id, 
              project_name: project_name,
              project_description : project_description,
              type_operation : type_operation }),
    }).then((_res) => {
      window.location.href = "/projectdata";
  })