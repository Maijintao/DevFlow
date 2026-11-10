from app.services.github.client import GitHubClient


async def list_issues(owner: str, repo: str, token: str | None = None, limit: int = 30, base_url: str | None = None) -> list[dict]:
    client = GitHubClient(token, base_url)
    items = await client.get(f"/repos/{owner}/{repo}/issues", {"state": "all", "per_page": limit})
    return [item for item in items if "pull_request" not in item]


async def list_updated_issues(owner: str, repo: str, token: str | None, base_url: str | None, since: str | None) -> list[dict]:
    params = {"state": "all", "sort": "updated", "direction": "asc"}
    if since:
        params["since"] = since
    items = await GitHubClient(token, base_url).get_all(f"/repos/{owner}/{repo}/issues", params)
    return [item for item in items if "pull_request" not in item]
