# OPL usage counting

Usage counting is **not** part of the scientific dependency chain.

The Reference Labs must remain fully usable when analytics are disabled, blocked, offline, or removed.

## Default

`site/config.js` ships with analytics disabled.

No pageview or user information is sent anywhere in the default source tree.

## Optional public aggregate counter

The small adapter in `site/analytics.js` supports two optional URLs:

- `countEndpoint` — an endpoint that records a page view with a `?p=<path>` query.
- `publicCounterJson` — a public JSON counter URL. Use `{path}` as a placeholder for the encoded page path.

A privacy-preserving open-source service such as GoatCounter can supply both behaviors, but the provider must be explicitly configured by the maintainer. OPL should not add cookies, persistent user identifiers, fingerprinting, advertising analytics, or mandatory third-party scripts.

The visible number should be described as **recorded uses/page views**, not as a precise count of unique human learners unless the chosen analytics method actually supports that claim.

## Decentralization rule

Removing the analytics configuration must not change any Reference Lab function, validation result, offline package, or publication-linked analysis.
