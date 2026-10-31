// Read only the generated catalog header; page data can be very large.
import {open} from 'node:fs/promises';
const file=await open('games/book/book_pages.zi','r');
let header;
try { const bytes=Buffer.alloc(4096); const {bytesRead}=await file.read(bytes,0,bytes.length,0); header=bytes.subarray(0,bytesRead).toString('utf8'); } finally { await file.close(); }
function array(name) {
 const match=header.match(new RegExp(name+String.raw`:[^=]*= \.[\[{](.*?)[\]}];`));
 if(!match)throw Error('Missing catalog header '+name);
 return JSON.parse('['+match[1]+']');
}
export const bookIds=array('category_ids'), pageCounts=array('category_counts');
const order=array('shelf_order'), starts=array('group_starts'), counts=array('group_counts');
export function bookPosition(id,width,height) {
 const category=bookIds.indexOf(id), offset=order.indexOf(category);
 const group=starts.findIndex((start,i)=>offset>=start&&offset<start+counts[i]);
 if(category<0||group<0)throw Error('Unknown book '+id);
 const fit=Math.min(width/320,(height-56)/200), pad=Math.max(24,Math.trunc(14*fit)+12);
 const columns=width<600?3:starts.length, tabWidth=(width-2*pad-8*(columns-1))/columns;
 return {index:offset-starts[group],x:pad+(group%columns)*(tabWidth+8)+tabWidth/2,y:56+pad+Math.floor(group/columns)*52+22};
}
