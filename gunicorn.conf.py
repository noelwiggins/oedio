# Gunicorn hooks. The Darwin World thread must start inside the worker process
# (threads started in the --preload master do not survive the fork).


def post_worker_init(worker):
    try:
        from darwin.web import start_background
        start_background()
    except Exception as e:  # never stop the site from serving because of Darwin
        worker.log.error(f"[darwin] background start failed: {e!r}")
