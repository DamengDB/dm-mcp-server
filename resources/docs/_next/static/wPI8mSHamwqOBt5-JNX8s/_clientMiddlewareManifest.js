self.__MIDDLEWARE_MATCHERS = [
  {
    "regexp": "^\\/dm-mcp\\/docs(?:\\/(_next\\/data\\/[^/]{1,}))?\\/_pagefind(\\.json|\\.rsc|\\.segments\\/.+\\.segment\\.rsc)?[\\/#\\?]?$",
    "originalSource": "/_pagefind"
  },
  {
    "regexp": "^\\/dm-mcp\\/docs(?:\\/(_next\\/data\\/[^/]{1,}))?\\/_pagefind(?:\\/((?:[^\\/#\\?]+?)(?:\\/(?:[^\\/#\\?]+?))*))?(\\.json|\\.rsc|\\.segments\\/.+\\.segment\\.rsc)?[\\/#\\?]?$",
    "originalSource": "/_pagefind/:path*"
  },
  {
    "regexp": "^\\/dm-mcp\\/docs(?:\\/(_next\\/data\\/[^/]{1,}))?\\/dm-mcp\\/docs\\/_pagefind(\\.json|\\.rsc|\\.segments\\/.+\\.segment\\.rsc)?[\\/#\\?]?$",
    "originalSource": "/dm-mcp/docs/_pagefind"
  },
  {
    "regexp": "^\\/dm-mcp\\/docs(?:\\/(_next\\/data\\/[^/]{1,}))?\\/dm-mcp\\/docs\\/_pagefind(?:\\/((?:[^\\/#\\?]+?)(?:\\/(?:[^\\/#\\?]+?))*))?(\\.json|\\.rsc|\\.segments\\/.+\\.segment\\.rsc)?[\\/#\\?]?$",
    "originalSource": "/dm-mcp/docs/_pagefind/:path*"
  },
  {
    "regexp": "^\\/dm-mcp\\/docs(?:\\/(_next\\/data\\/[^/]{1,}))?\\/dm-mcp\\/docs\\/0-pagefind(\\.json|\\.rsc|\\.segments\\/.+\\.segment\\.rsc)?[\\/#\\?]?$",
    "originalSource": "/dm-mcp/docs/0-pagefind"
  },
  {
    "regexp": "^\\/dm-mcp\\/docs(?:\\/(_next\\/data\\/[^/]{1,}))?\\/dm-mcp\\/docs\\/0-pagefind(?:\\/((?:[^\\/#\\?]+?)(?:\\/(?:[^\\/#\\?]+?))*))?(\\.json|\\.rsc|\\.segments\\/.+\\.segment\\.rsc)?[\\/#\\?]?$",
    "originalSource": "/dm-mcp/docs/0-pagefind/:path*"
  }
];self.__MIDDLEWARE_MATCHERS_CB && self.__MIDDLEWARE_MATCHERS_CB()