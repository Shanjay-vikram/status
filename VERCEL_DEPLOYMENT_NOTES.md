# Vercel deployment notes for HardwareCare

This package adds a Vercel Python Function entry point (`api/index.py`) and
routing configuration (`vercel.json`) to address a 404 caused by a Flask app
without a serverless entry point.

## Deploy
1. Push the contents of this folder (the folder containing `vercel.json`,
   `requirements.txt`, `api/`, and `app/`) to the GitHub repository root.
2. In Vercel, import that repository. Set Root Directory to the folder that
   contains `vercel.json` (not its parent).
3. Do not set a static output directory. Deploy using Python build detection.
4. Add environment variables:
   - `SECRET_KEY`: a long random secret
   - `DATABASE_URL`: a hosted PostgreSQL connection URL
5. Redeploy after setting environment variables.

## Important limitations
This fixes the Flask serverless entry-point/routing configuration only.
SQLite and Vercel function filesystems are not persistent storage for business
data, uploads, or reports. The current application stores uploads/reports in
local folders; migrate these to durable object storage before real customer use.
Create the first Admin against the hosted database using a secure one-off setup.
The local `create_admin.py` command does not run automatically on Vercel.

Test database connectivity, login, static assets, uploads, PDF reports,
approval permissions and customer data isolation before sharing the URL.
This is a development build, not production-certified.
