import sites from '../lib/sites.json';

sites.sort((a, b) => (
  a.publication_date > b.publication_date ? -1 : 1
))
export async function load() {
  return {
    sites
  };
}