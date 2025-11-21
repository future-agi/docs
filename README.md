# Future AGI Documentation

This repository contains the official documentation for Future AGI products and services. The documentation is built using [Mintlify](https://mintlify.com), a modern documentation platform.


## Local Development

### Prerequisites

- Node.js 14 or higher
- npm or yarn

### Setup

1. Clone this repository
```bash
git clone <repository-url>
cd docs
```

2. Install dependencies
```bash
npm install
```

3. Run the development server
```bash
mint dev
```

4. View the documentation at `http://localhost:3000`

## Documentation Standards

All documentation in this repository follows specific standards defined in our [.cursorrules](./.cursorrules) file. Key conventions include:

- **File Structure**: Media files must be in `/screenshot/<complete-relative-path-of-the-respective-page>`
- **Naming**: Pages should have comprehensive names that convey their purpose
- **SEO**: Each page must include title and description tags
- **Code Samples**: Multi-language code snippets use `code-groups`
- **Clarity**: Complex terminology uses tooltip tags with "learn more" links
- **Product Structure**: Each product section includes overview, quickstart, and how-to guides

## Contributing

### Before Making Changes

1. Create a new branch from `dev`
2. Make your changes following the documentation standards

### Before Publishing

1. Add redirects for any URLs that are being removed or updated
2. Check for broken links with `mint broken-links`
3. Ensure all screenshots are in the correct location
4. Verify that pages have proper title and description tags

### Pull Request Process

1. Ensure your changes adhere to our documentation standards
2. Update the Table of Contents if necessary
3. Request review from the documentation team

## Deployment

The documentation follows this workflow:
1. Changes are merged to the `dev` branch for testing
2. Once approved, changes are merged from `dev` to `main`
3. The documentation is automatically deployed when changes are merged to the main branch


---