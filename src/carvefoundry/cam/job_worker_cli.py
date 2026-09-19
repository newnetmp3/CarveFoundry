"""Execute one isolated job without redefining pickled request classes."""

from carvefoundry.cam.job_process import main

if __name__ == "__main__":
    raise SystemExit(main())
