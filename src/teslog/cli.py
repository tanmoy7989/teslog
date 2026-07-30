import click
import uvicorn

from teslog.config import get_settings


@click.command()
def main() -> None:
    """Run the Teslog web server."""
    settings = get_settings()
    uvicorn.run(
        "teslog.app:app",
        host=settings.teslog_host,
        port=settings.teslog_port,
        reload=settings.teslog_reload,
    )


if __name__ == "__main__":
    main()
