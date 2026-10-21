FROM cinelab-offline/api:1.3.0-a1
WORKDIR /app
# The offline course API already pins the runtime and all lockfile dependencies.
# Reusing it lets source-only student changes build without Docker Hub access.
COPY backend/ backend/
COPY recommender/ recommender/
COPY scripts/student_package.py scripts/student_package.py
COPY deployment/*.py deployment/
