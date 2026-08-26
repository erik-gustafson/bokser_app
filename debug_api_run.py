import uvicorn

if __name__ == "__main__":
    uvicorn.run(
        "src.api.main:app",  # module:variable
        host="0.0.0.0",
        port=8005,
        log_level="info",
        use_colors=False,
        workers=1,
    )
