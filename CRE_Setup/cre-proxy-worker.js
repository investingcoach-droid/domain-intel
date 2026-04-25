/**
 * CRE Business Intel — Cloudflare Worker Proxy
 * Forwards GraphQL requests to CommercialRealEstate.com.au
 * 
 * Usage: GET /?agencyId=20869&pageNo=1
 * Returns: JSON with business listing adIDs
 * 
 * Deploy to: cre-proxy.stan-7a2.workers.dev
 */

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    const agencyId = parseInt(url.searchParams.get('agencyId'));
    const pageNo = parseInt(url.searchParams.get('pageNo') || '1');

    if (!agencyId) {
      return new Response(JSON.stringify({ error: 'agencyId required' }), {
        status: 400, headers: { 'content-type': 'application/json' }
      });
    }

    const query = "query agencyListingsQuery($searchType: Int!, $pageNo: Int!, $pageSize: Int!, $agencyIds: [Int]) { searchListings( searchType: $searchType pageNumber: $pageNo pageSize: $pageSize sortingOption: null categories: null priceFrom: null priceTo: null buildingSizeFrom: null buildingSizeTo: null landSizeFrom: null landSizeTo: null states: null regionIds: null areaIds: null suburbIds: null adIds: null keywords: null saleMethod: null detailsAdId: null boundingBox: null occupancyStatus: null carSpaces: null agencyIds: $agencyIds featureFlags: null ) { totalItemsCount totalPages pagedSearchResults { ... on BusinessListingType { adID searchType } ... on PropertyListingType { adID searchType } __typename } __typename } }";

    const response = await fetch('https://www.commercialrealestate.com.au/bf/api/gqlb', {
      method: 'POST',
      headers: {
        'content-type': 'application/json',
        'accept': 'application/json',
        'referer': 'https://www.commercialrealestate.com.au/',
        'user-agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/147.0.0.0 Safari/537.36'
      },
      body: JSON.stringify({
        operationName: 'agencyListingsQuery',
        variables: { agencyIds: [agencyId], searchType: 0, pageNo: pageNo, pageSize: 6 },
        query: query
      })
    });

    const data = await response.json();
    return new Response(JSON.stringify(data), {
      headers: {
        'content-type': 'application/json',
        'access-control-allow-origin': '*'
      }
    });
  }
};
