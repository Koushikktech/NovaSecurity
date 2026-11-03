export async function saveAll(urls: string[]) {
  urls.forEach(async url => {
    await fetch(url);
  });
}
