exports.saveAll = async function saveAll(items) {
  items.forEach(async item => { await item.save(); });
};
