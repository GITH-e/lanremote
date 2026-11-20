package cn.lanremote;

/** Relative touchpad position, independent of Android so its geometry can be tested. */
public final class PointerPosition {
    public float x=.5f, y=.5f;
    public void set(float nx,float ny){x=clamp(nx);y=clamp(ny);}
    public void move(float dx,float dy,float imageWidth,float imageHeight,float sensitivity){
        if(imageWidth<=0||imageHeight<=0)return;
        set(x+dx*sensitivity/imageWidth,y+dy*sensitivity/imageHeight);
    }
    private static float clamp(float value){return Math.max(0,Math.min(1,value));}
}
