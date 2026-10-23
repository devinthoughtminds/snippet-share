async def test_api_docs_are_served(client):
    response = await client.get("/api/docs")
    assert response.status_code == 200
