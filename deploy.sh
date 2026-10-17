#!/usr/bin/env bash
# One-command deploy of Saathi to Google Cloud Run. Run it from Google Cloud Shell
# (or any machine with gcloud) inside the cloned repository:  ./deploy.sh
#
# What it does:
#   1. Enables the required Google Cloud APIs.
#   2. Stores your Gemini API key in Secret Manager (asked with hidden input, never echoed).
#   3. Builds the container with Cloud Build and deploys it to Cloud Run (Mumbai region).
#   4. Prints the public URL and checks that it is healthy.
set -euo pipefail

REGION="${REGION:-asia-south1}"
SERVICE="${SERVICE:-saathi}"
SECRET_NAME="GEMINI_API_KEY"
MODEL="${GEMINI_MODEL:-gemini-3.8-flash}"

PROJECT_ID="${PROJECT_ID:-$(gcloud config get-value project 2>/dev/null || true)}"
if [[ -z "${PROJECT_ID}" ]]; then
  read -rp "Google Cloud project ID: " PROJECT_ID
fi
gcloud config set project "${PROJECT_ID}" >/dev/null
echo "Deploying '${SERVICE}' to project '${PROJECT_ID}' in ${REGION}"

echo "Enabling APIs (first run can take a minute)..."
gcloud services enable \
  run.googleapis.com \
  cloudbuild.googleapis.com \
  artifactregistry.googleapis.com \
  secretmanager.googleapis.com

if gcloud secrets describe "${SECRET_NAME}" >/dev/null 2>&1; then
  echo "Secret ${SECRET_NAME} already exists. To replace the key later run:"
  echo "  printf '%s' 'NEW_KEY' | gcloud secrets versions add ${SECRET_NAME} --data-file=-"
else
  read -rsp "Paste your Gemini API key (input is hidden): " GEMINI_KEY
  echo
  if [[ -z "${GEMINI_KEY}" ]]; then
    echo "No key entered. Create one at https://aistudio.google.com/api-keys and run ./deploy.sh again." >&2
    exit 1
  fi
  printf '%s' "${GEMINI_KEY}" | gcloud secrets create "${SECRET_NAME}" \
    --replication-policy=automatic --data-file=-
  unset GEMINI_KEY
fi

PROJECT_NUMBER="$(gcloud projects describe "${PROJECT_ID}" --format='value(projectNumber)')"
RUNTIME_SA="${PROJECT_NUMBER}-compute@developer.gserviceaccount.com"

# Least privilege: the runtime can read only this one secret.
gcloud secrets add-iam-policy-binding "${SECRET_NAME}" \
  --member="serviceAccount:${RUNTIME_SA}" \
  --role="roles/secretmanager.secretAccessor" >/dev/null
# Source deploys build with the default compute service account on newer projects.
gcloud projects add-iam-policy-binding "${PROJECT_ID}" \
  --member="serviceAccount:${RUNTIME_SA}" \
  --role="roles/run.builder" --condition=None >/dev/null

echo "Building and deploying (about 3-5 minutes)..."
gcloud run deploy "${SERVICE}" \
  --source . \
  --region "${REGION}" \
  --allow-unauthenticated \
  --set-secrets "GEMINI_API_KEY=${SECRET_NAME}:latest" \
  --set-env-vars "GEMINI_MODEL=${MODEL}" \
  --memory 512Mi \
  --cpu 1 \
  --concurrency 40 \
  --min-instances 0 \
  --max-instances 3 \
  --timeout 60

URL="$(gcloud run services describe "${SERVICE}" --region "${REGION}" --format='value(status.url)')"
echo
echo "Live at: ${URL}"
echo "Health check:"
curl -fsS "${URL}/api/health" && echo
