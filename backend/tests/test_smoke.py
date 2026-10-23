async def test_api_docs_are_served(client):
    response = await client.get("/api/docs")
    assert response.status_code == 200


async def test_openapi_documents_real_status_codes(client):
    paths = (await client.get("/api/openapi.json")).json()["paths"]

    create = paths["/api/v1/pastes"]["post"]["responses"]
    assert {"201", "413", "422"} <= create.keys()
    assert create["201"]["content"]["application/json"]["schema"]["$ref"].endswith("/PasteCreated")

    read = paths["/api/v1/pastes/{paste_id}"]["get"]["responses"]
    assert {"200", "404"} <= read.keys()

    raw = paths["/api/v1/pastes/{paste_id}/raw"]["get"]["responses"]
    assert {"200", "404"} <= raw.keys()
    assert "text/plain" in raw["200"]["content"]
