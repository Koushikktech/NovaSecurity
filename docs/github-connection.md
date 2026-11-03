# GitHub connection

Proofline supports one trusted operator per backend. A connection belongs to that operator, not separate visitor accounts. Deploy behind the operator token; do not share it with unrelated users. GitHub tokens stay in server memory and expire or disappear on restart. Disconnect forgets the local token; revoke the app in GitHub settings to revoke authorization at GitHub as well.

## Register and configure

1. Register a GitHub App in GitHub developer settings. Set Homepage URL to your frontend and User authorization callback URL to `http://localhost:8000/api/v1/github/callback` for local development.
2. Set repository permissions **Contents: Read-only**, **Pull requests: Read-only**, with Metadata read access. Enable user authorization and install the app on selected repositories. Webhooks are unnecessary for manual reviews; disable Active if unused. The connection supports expiring user tokens; when expired, reconnect (automatic refresh is not implemented).
3. Set these backend environment variables, then restart the backend:

```dotenv
GITHUB_APP_CLIENT_ID=your_app_client_id
GITHUB_APP_CLIENT_SECRET=your_app_client_secret
GITHUB_APP_CALLBACK_URL=http://localhost:8000/api/v1/github/callback
GITHUB_APP_INSTALL_URL=https://github.com/apps/your-app-slug/installations/new
PROOFLINE_FRONTEND_URL=http://localhost:3000
```

For hosting, use HTTPS callback/frontend URLs, configure allowed frontend origins, and set `PROOFLINE_OPERATOR_TOKEN`.

## Use

Choose **Pick from GitHub**, connect, pick a repository, then a branch, open PR or commit. Branch selection pins the selected SHA. Private repositories use the connected credential during cloning and PR metadata reads; credentials are passed through Git's environment configuration, never stored in remote URLs or command arguments. Repository and target lists are paginated. Search filters loaded repositories; load more to search further.

Alternatively choose **Paste a link**: repository, branch/tree, PR, commit and comparison URLs are detected automatically. Local folder upload is a primary source option. Quick/deep controls are under Scope options.

Connected credentials grant read access for review. Existing GitHub publication uses the separately configured operator `GITHUB_TOKEN` and publish flag. Connecting does not enable write actions.

## Verification boundaries

Automated tests cover authorization state expiry/replay, callback credential exchange, credential propagation, and repository target responses using mocked GitHub. A real registration, authorization and private repository review must be tested with your app credentials before demonstrating them. No GitHub App has been registered by this code change.
