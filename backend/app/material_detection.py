"""Conservative pixel-derived outlines. No learned masks or physical scale inference.

One isolated, fully visible sheet on a contrasting background is supported.
Unresolved holes, competing pieces, touching image edges and weak separation fail
closed. Approximate vision boxes guide seeds only; they never become an outline.
"""
import io
import threading
from PIL import Image, ImageOps, UnidentifiedImageError

MAX_IMAGE_BYTES=8*1024*1024
_CV_LOCK=threading.Lock()

class DetectionError(ValueError):
    pass

def decode_photo(data, mime):
    if len(data)>MAX_IMAGE_BYTES:raise DetectionError('image_too_large')
    if mime not in ('image/jpeg','image/png','image/webp'):raise DetectionError('unsupported_image_type')
    try:
        with Image.open(io.BytesIO(data)) as source:
            if source.format not in ('JPEG','PNG','WEBP') or Image.MIME.get(source.format)!=mime:
                raise DetectionError('invalid_image')
            if min(source.size)<48 or max(source.size)>8192 or source.width*source.height>16_000_000:
                raise DetectionError('invalid_image_dimensions')
            source.verify()
        with Image.open(io.BytesIO(data)) as source:
            oriented=ImageOps.exif_transpose(source)
            # Transparent pixels are not material. Flatten consistently for display/vision.
            rgba=oriented.convert('RGBA')
            rgb=Image.new('RGB',rgba.size,'white');rgb.paste(rgba,mask=rgba.getchannel('A'))
        return rgb
    except (UnidentifiedImageError,OSError,Image.DecompressionBombError,Image.DecompressionBombWarning):
        raise DetectionError('invalid_image') from None

def vision_image(photo):
    """Strip metadata, bound vision pixels and payload; retain original coordinate ratio."""
    image=photo.copy();image.thumbnail((1024,1024),Image.Resampling.LANCZOS)
    out=io.BytesIO();image.save(out,'JPEG',quality=80,optimize=True)
    data=out.getvalue()
    if len(data)>1024*1024:raise DetectionError('vision_image_too_large')
    return data

def detect_outline(photo, guidance=None):
    # OpenCV's RNG is process-global. Serialize the bounded CPU operation, also
    # across cancellation, rather than leaving cancelled worker jobs unbounded.
    if not _CV_LOCK.acquire(blocking=False):raise DetectionError('detection_busy')
    try:
        import cv2
        try:return _detect(photo,guidance)
        except cv2.error:raise DetectionError('foreground_not_clear') from None
    finally:_CV_LOCK.release()

def _detect(photo,guidance):
    import cv2
    import numpy as np
    from shapely.geometry import Polygon, box, mapping
    if guidance and (not guidance['flat_for_cutting'] or guidance['issues']):
        raise DetectionError('photo_not_suitable')
    small=photo.copy();small.thumbnail((768,768),Image.Resampling.LANCZOS)
    rgb=np.asarray(small);height,width=rgb.shape[:2]
    cv2.setNumThreads(1);cv2.setRNGSeed(0)
    lab=cv2.cvtColor(rgb,cv2.COLOR_RGB2LAB).astype(np.float32)
    band=max(2,min(width,height)//40)
    border=np.concatenate((lab[:band].reshape(-1,3),lab[-band:].reshape(-1,3),
                           lab[:,:band].reshape(-1,3),lab[:,-band:].reshape(-1,3)))
    # Several actual border colours accommodate gradients and patterned surfaces.
    sample=np.ascontiguousarray(border[::max(1,len(border)//2048)])
    _,labels,centres=cv2.kmeans(sample,3,None,(cv2.TERM_CRITERIA_EPS+cv2.TERM_CRITERIA_MAX_ITER,20,.2),1,cv2.KMEANS_PP_CENTERS)
    distances=np.min(np.linalg.norm(lab[:,:,None,:]-centres[None,None,:,:],axis=3),axis=2)
    border_dist=np.min(np.linalg.norm(border[:,None,:]-centres[None,:,:],axis=2),axis=1)
    threshold=max(12.,float(np.percentile(border_dist,95))+8.)
    try:
        if threshold>55:raise DetectionError('background_too_complex')
        result,_=_outline_from_contrast(photo,rgb,lab,distances,threshold,guidance)
        return result
    except DetectionError as error:
        # Preserve clear topology/suitability refusals. Only weak colour separation
        # invokes the additional spatial hypotheses, never a lower area threshold.
        if str(error) not in ('foreground_not_clear','background_too_complex'):raise
        primary_error=error
    return _interior_background_outline(photo,rgb,guidance,primary_error)

def _interior_background_outline(photo,rgb,guidance,primary_error):
    """A tabletop at the frame can share a colour with enclosed material.

    Learn a bounded set of image-wide background colours, require each background
    hypothesis to have broad spatial/frame support, then remove frame-connected
    exterior regions. Never choose a foreground by colour alone or from a box.
    """
    import cv2
    import numpy as np
    lab=cv2.medianBlur(cv2.cvtColor(rgb,cv2.COLOR_RGB2LAB),3).astype(np.float32)
    height,width=lab.shape[:2]
    flat=lab.reshape(-1,3);sample=flat[::max(1,len(flat)//4096)].copy()
    cv2.setRNGSeed(0)
    _,labels,centres=cv2.kmeans(sample,4,None,(cv2.TERM_CRITERIA_EPS+cv2.TERM_CRITERIA_MAX_ITER,30,.2),1,cv2.KMEANS_PP_CENTERS)
    results=[]
    for index,centre in enumerate(centres):
        residual=np.linalg.norm(sample[labels.ravel()==index]-centre,axis=1)
        if not len(residual):continue
        threshold=max(12.,float(np.percentile(residual,95))+8.)
        if threshold>55:continue
        distances=np.linalg.norm(lab-centre,axis=2)
        background=distances<=threshold
        frame=np.concatenate((background[0],background[-1],background[:,0],background[:,-1]))
        quadrants=[background[:height//2,:width//2],background[:height//2,width//2:],
                   background[height//2:,:width//2],background[height//2:,width//2:]]
        if background.mean()<.25 or frame.mean()<.05 or sum(q.mean()>.1 for q in quadrants)<3:continue
        try:
            result,mask=_outline_from_contrast(photo,rgb,lab,distances,threshold,guidance,spatial=True)
            results.append((float(background.mean()),result,mask))
        except DetectionError as error:
            # An alternative colour interpretation must not hide competing pieces,
            # a cut-out, incomplete edges, or a malformed contour.
            if str(error)!='foreground_not_clear':raise
    if not results:raise primary_error
    results.sort(key=lambda item:-item[0])
    _,result,mask=results[0]
    for _,_,other in results[1:]:
        intersection=np.count_nonzero(mask&other);union=np.count_nonzero(mask|other)
        if intersection/max(union,1)<.9:raise DetectionError('foreground_not_clear')
    return result

def _outline_from_contrast(photo,rgb,lab,distances,threshold,guidance,spatial=False):
    import cv2
    import numpy as np
    from shapely.geometry import Polygon, box, mapping
    height,width=rgb.shape[:2];band=max(2,min(width,height)//40)
    candidate=(distances>threshold).astype(np.uint8)
    if spatial:
        # Break thin mat-grid/loose-thread bridges before spatial connectivity.
        candidate=cv2.morphologyEx(candidate,cv2.MORPH_OPEN,np.ones((3,3),np.uint8))
    allowed=None
    if guidance:
        x0,y0,x1,y1=guidance['region']
        # Check consistency with the hint, never clip a foreground to a model box.
        allowed=np.zeros_like(candidate)
        left=max(0,int((x0-.06)*width));right=min(width,int((x1+.06)*width)+1)
        top=max(0,int((y0-.06)*height));bottom=min(height,int((y1+.06)*height)+1)
        allowed[top:bottom,left:right]=1
    candidate=cv2.morphologyEx(candidate,cv2.MORPH_CLOSE,np.ones((3,3),np.uint8))
    count,components,stats,_=cv2.connectedComponentsWithStats(candidate,8)
    areas=sorted(((int(stats[i,cv2.CC_STAT_AREA]),i) for i in range(1,count)),reverse=True)
    if spatial:
        def enclosed(index):
            x,y,w,h,_=stats[index]
            return x>2 and y>2 and x+w<width-2 and y+h<height-2
        areas=[(area,index) for area,index in areas if enclosed(index)]
    frame=height*width
    if not areas or areas[0][0]<frame*.03:raise DetectionError('foreground_not_clear')
    area,index=areas[0]
    if len(areas)>1 and areas[1][0]>max(frame*.01,area*.08):raise DetectionError('multiple_material_pieces')
    component=(components==index).astype(np.uint8)
    if allowed is not None and np.count_nonzero(component*allowed)/area<.95:
        raise DetectionError('guidance_region_incomplete')
    if area>frame*.88:raise DetectionError('foreground_fills_frame')
    margin=2 if spatial else band
    if component[:margin].any() or component[-margin:].any() or component[:,:margin].any() or component[:,-margin:].any():
        raise DetectionError('material_edge_missing')
    eroded=cv2.erode(component,np.ones((5,5),np.uint8))
    if int(eroded.sum())<frame*.01:raise DetectionError('foreground_not_clear')
    seeds=np.full((height,width),cv2.GC_BGD,dtype=np.uint8)
    neighbourhood=cv2.dilate(component,np.ones((15,15),np.uint8))>0
    seeds[neighbourhood]=cv2.GC_PR_BGD
    seeds[component>0]=cv2.GC_PR_FGD
    core=eroded>0
    if spatial:
        # A thin connected grid/shadow patch is not a certain foreground seed.
        # Use the robust interior colour for definite seeds; GrabCut can still
        # recover other material colours from probable foreground pixels.
        foreground_colour=np.median(lab[core],axis=0)
        foreground_distance=np.linalg.norm(lab-foreground_colour,axis=2)
        seed_threshold=max(12.,float(np.percentile(foreground_distance[core],80))+6.)
        core&=foreground_distance<seed_threshold
        if np.count_nonzero(core)<frame*.01:raise DetectionError('foreground_not_clear')
    seeds[core]=cv2.GC_FGD
    cv2.grabCut(cv2.cvtColor(rgb,cv2.COLOR_RGB2BGR),seeds,None,np.zeros((1,65),np.float64),np.zeros((1,65),np.float64),3,cv2.GC_INIT_WITH_MASK)
    mask=np.isin(seeds,(cv2.GC_FGD,cv2.GC_PR_FGD)).astype(np.uint8)
    if spatial:mask=cv2.morphologyEx(mask,cv2.MORPH_OPEN,np.ones((3,3),np.uint8))
    # Remove tiny isolated specks only. Never fill a real internal cut-out.
    n,parts,stats,_=cv2.connectedComponentsWithStats(mask,8)
    ordered=sorted(((int(stats[i,cv2.CC_STAT_AREA]),i) for i in range(1,n)),reverse=True)
    if not ordered:raise DetectionError('foreground_not_clear')
    if len(ordered)>1 and ordered[1][0]>frame*.005:raise DetectionError('multiple_material_pieces')
    mask=(parts==ordered[0][1]).astype(np.uint8)
    contours,hierarchy=cv2.findContours(mask,cv2.RETR_CCOMP,cv2.CHAIN_APPROX_SIMPLE)
    if hierarchy is None:raise DetectionError('foreground_not_clear')
    # Even small resolved holes are unsafe to silently bridge with cutting paths.
    for i,c in enumerate(contours):
        if hierarchy[0,i,3]>=0 and cv2.contourArea(c)>=4:raise DetectionError('internal_holes_unsupported')
    _assert_single_surface(rgb,mask)
    external=[c for i,c in enumerate(contours) if hierarchy[0,i,3]<0]
    contour=max(external,key=cv2.contourArea)
    approx=cv2.approxPolyDP(contour,max(.6,cv2.arcLength(contour,True)*.0015),True)
    if not 3<=len(approx)<=100:raise DetectionError('contour_too_complex')
    px=approx[:,0,:].astype(float)
    px[:,0]*=photo.width/width;px[:,1]*=photo.height/height
    polygon=Polygon(px)
    if not polygon.is_valid or polygon.is_empty or polygon.area<photo.width*photo.height*.03:
        raise DetectionError('invalid_detected_geometry')
    if polygon.area>photo.width*photo.height*.88 or not box(1,1,photo.width-1,photo.height-1).contains(polygon):
        raise DetectionError('material_edge_missing')
    reference=Polygon(contour[:,0,:])
    simplified=Polygon(approx[:,0,:])
    if not reference.is_valid:raise DetectionError('contour_too_complex')
    if reference.symmetric_difference(simplified).area/max(reference.area,1)>.025:
        raise DetectionError('contour_too_complex')
    if float(np.median(distances[mask>0]))<threshold+5:raise DetectionError('foreground_not_clear')
    return {'geometry_px':mapping(polygon),'width_px':photo.width,'height_px':photo.height,
            'area_px2':polygon.area,'requires_confirmation':True,
            'quality':{'method':'spatial_background_and_grabcut' if spatial else 'contrast_and_grabcut','confidence':None,
                       'note':'Approximate pixel outline; inspect the complete edge before accepting.'}},mask

def _conflicting_surface_regions(rgb,mask):
    """Pixel evidence of substantial, localized surfaces inside a silhouette.

    This is an ambiguity gate, not semantic tool recognition. Repeated small print
    elements are allowed. Large coherent regions with strong local colour changes
    can be occluders or a compound scene; do not call their enclosing mat material.
    Boundary seams/shadows are excluded using an inner support ring.
    """
    import cv2
    import numpy as np
    lab=cv2.medianBlur(cv2.cvtColor(rgb,cv2.COLOR_RGB2LAB),5).astype(np.float32)
    pixels=lab[mask>0];sample=pixels[::max(1,len(pixels)//4096)].copy()
    if len(sample)<6:return []
    if np.percentile(np.linalg.norm(sample-np.median(sample,axis=0),axis=1),95)<15:return []
    cv2.setRNGSeed(0)
    _,_,centres=cv2.kmeans(sample,6,None,(cv2.TERM_CRITERIA_EPS+cv2.TERM_CRITERIA_MAX_ITER,30,.2),1,cv2.KMEANS_PP_CENTERS)
    classes=np.argmin(np.linalg.norm(lab[:,:,None,:]-centres[None,None,:,:],axis=3),axis=2)
    inner=cv2.erode(mask,np.ones((15,15),np.uint8))>0
    total=max(int(mask.sum()),1);regions=[]
    for index in range(len(centres)):
        colour=((classes==index)&(mask>0)).astype(np.uint8)
        colour=cv2.morphologyEx(colour,cv2.MORPH_OPEN,np.ones((5,5),np.uint8))
        n,parts,stats,_=cv2.connectedComponentsWithStats(colour,8)
        for component in range(1,n):
            fraction=float(stats[component,cv2.CC_STAT_AREA])/total
            if fraction<.025:continue
            pixels_in_region=parts==component
            if np.count_nonzero(pixels_in_region&inner)/stats[component,cv2.CC_STAT_AREA]<.97:continue
            rim=(cv2.dilate(pixels_in_region.astype(np.uint8),np.ones((9,9),np.uint8))>0)&(~pixels_in_region)&(mask>0)
            if not rim.any():continue
            contrast=float(np.linalg.norm(np.median(lab[rim],axis=0)-np.median(lab[pixels_in_region],axis=0)))
            if contrast<30:continue
            cs,_=cv2.findContours(pixels_in_region.astype(np.uint8),cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)
            regions.append({'fraction':fraction,'contrast_lab':contrast,'contour':max(cs,key=cv2.contourArea)[:,0,:]})
    return regions

def _assert_single_surface(rgb,mask):
    regions=_conflicting_surface_regions(rgb,mask)
    if any(r['fraction']>=.08 for r in regions) or (len(regions)>=2 and sum(r['fraction'] for r in regions)>=.05):
        raise DetectionError('material_scene_ambiguous')
