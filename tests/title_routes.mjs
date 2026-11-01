// Keyboard navigation follows the painted items in the tested scene data.
// Kept independent of CDP so every browser gate uses its existing key sender.
export function titleKeys(data, title) {
  if (!data?.scenes?.length) throw Error('Missing painted title scenes');
  const names = data.scenes.map(scene => scene.name);
  const paths = new Map([[0, []]]), queue = [0];
  while (queue.length) {
    const sceneIndex = queue.shift(), scene = data.scenes[sceneIndex];
    if (scene.portrait && (scene.hotspots.length !== scene.portrait.hotspots.length ||
        scene.hotspots.some((spot, index) =>
          spot.id !== scene.portrait.hotspots[index]?.id ||
          spot.target !== scene.portrait.hotspots[index]?.target))) {
      throw Error('Title keyboard order differs by orientation: ' + scene.name);
    }
    for (const [index, spot] of scene.hotspots.entries()) {
      const [kind, target] = spot.target.split(':');
      const path = [...paths.get(sceneIndex), String(index + 1)];
      if ((kind === 'game' && target === title) ||
          (kind === 'book' && target === 'sweet-porridge' && title === 'Sweet Porridge')) {
        return ['Home', ...path];
      }
      if (kind === 'scene') {
        const next = names.indexOf(target);
        if (next < 0) throw Error('Unknown title scene: ' + target);
        if (!paths.has(next)) { paths.set(next, path); queue.push(next); }
      }
    }
  }
  throw Error('No painted title route opens ' + title);
}

export async function openTitleGame(data, title, key) {
  for (const value of titleKeys(data, title)) await key(value);
}

export function titleUnit(width, height) {
  return Math.max(1, Math.min(3, Math.min(width, height) / 300));
}
