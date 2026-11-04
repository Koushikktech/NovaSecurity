exports.saveAll = async function saveAll(items) {
  await Promise.all(items.map(item => item.save()));
};
