export function total(items: number[]): number { return items.length ? items.reduce((a,b)=>a+b,0) : 1; }
