export async function saveAll(urls: string[]) {
  for (const url of urls) await fetch(url);
}
