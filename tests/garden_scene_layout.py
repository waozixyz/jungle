"""Independent fixture coordinates inside approved Garden v3 painted soil."""

def soil_point(w,h,x,y):
    tray = 180 if w < 600 else 94
    portrait = w < h
    aw, ah = (1024,1536) if portrait else (1671,941)
    sw, sh = w, w*ah//aw
    if sh > h-tray: sh=h-tray; sw=sh*aw//ah
    ox, oy = (w-sw)//2, tray+(h-tray-sh)//2
    quads = ([[230,480],[415,520],[300,585],[95,535]], [[780,515],[960,555],[810,645],[605,590]], [[220,730],[415,790],[250,870],[65,800]], [[780,845],[950,900],[730,1040],[490,970]]) if portrait else ([[470,325],[690,352],[560,380],[310,350]], [[1170,360],[1480,392],[1330,435],[1020,393]], [[300,460],[600,510],[415,565],[130,510]], [[1190,540],[1500,600],[1190,695],[850,636]])
    left = 190-(y-410)*90//320
    u = ((x-500) if x>500 else (x-left))/(500-left)
    v = (y-(570 if y>570 else 410))/160
    q=quads[(2 if y>570 else 0)+(1 if x>500 else 0)]
    weights=((1-u)*(1-v),u*(1-v),u*v,(1-u)*v)
    nx,ny=(sum(a[i]*b for a,b in zip(q,weights)) for i in (0,1))
    return (ox+nx*sw/aw, oy+ny*sh/ah)
