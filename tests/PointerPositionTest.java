import cn.lanremote.PointerPosition;

public class PointerPositionTest {
    static void near(float actual,float expected){if(Math.abs(actual-expected)>.00001f)throw new AssertionError(actual+" != "+expected);}
    public static void main(String[] args){
        PointerPosition p=new PointerPosition();
        p.set(.3f,.4f);
        p.move(100,50,1000,500,1);near(p.x,.4f);near(p.y,.5f);
        // Lifting/repositioning the finger starts a new delta; it must not reset the cursor.
        p.move(100,0,1000,500,1);near(p.x,.5f);near(p.y,.5f);
        p.move(50,25,1000,500,2);near(p.x,.6f);near(p.y,.6f);
        p.move(10000,-10000,1000,500,1);near(p.x,1);near(p.y,0);
        p.move(-100,50,1000,500,1);near(p.x,.9f);near(p.y,.1f);
        // Same finger displacement has equal displayed x/y distance despite a wide desktop.
        p.set(.5f,.5f);p.move(40,40,800,450,1);near((p.x-.5f)*800,40);near((p.y-.5f)*450,40);
        p.move(100,100,0,0,1);near(p.x,.55f);
        System.out.println("Pointer geometry: 7 scenarios passed");
    }
}
