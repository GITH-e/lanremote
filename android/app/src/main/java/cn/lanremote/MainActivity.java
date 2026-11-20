package cn.lanremote;

import android.app.*;
import android.os.*;
import android.content.*;
import android.database.Cursor;
import android.graphics.*;
import android.net.Uri;
import android.provider.OpenableColumns;
import android.view.*;
import android.widget.*;
import org.json.*;
import java.io.*;
import java.net.*;
import java.security.*;
import java.security.cert.X509Certificate;
import java.util.*;
import java.util.concurrent.*;
import javax.net.ssl.*;

public class MainActivity extends Activity {
    final Handler ui = new Handler(Looper.getMainLooper());
    final ExecutorService controls = Executors.newSingleThreadExecutor();
    final ExecutorService frames = Executors.newSingleThreadExecutor();
    final ExecutorService files = Executors.newSingleThreadExecutor();
    volatile String token = "", address = "";
    volatile SSLSocketFactory tls;
    volatile boolean connected, connecting, foreground, frameBusy, clipBusy, transferring;
    final java.util.concurrent.atomic.AtomicBoolean movePending=new java.util.concurrent.atomic.AtomicBoolean();
    final java.util.concurrent.atomic.AtomicReference<float[]> latestMove=new java.util.concurrent.atomic.AtomicReference<>();
    EditText host, fingerprint, pin;
    TextView status, pendingLabel;
    LinearLayout root, login, remote;
    ScreenView screen;
    LinearLayout mouseButtons, mouseOptions;
    TextView mouseHint;
    Button modeButton;
    final PointerPosition pointer=new PointerPosition();
    boolean touchpad=true, fingerDown, gestureMoved, multiTouch, dragging;
    float previousX, previousY, startX, startY, scrollY, scrollRemainder;
    float sensitivity=1.4f;
    long touchStarted, lastInput, lastCursorPoll, lastDragHeartbeat;
    int touchSlop;
    final Runnable longPress=this::beginDrag;
    CheckBox autoClip, drag;
    ClipboardManager clipboard;
    String lastClip = null;
    final ArrayList<Uri> pending = new ArrayList<>();
    String downloadId;
    float lastX = .5f, lastY = .5f;
    long lastMove;
    final Runnable tick = new Runnable() {
        @Override public void run() {
            if (foreground && connected) {
                refreshFrame();
                if(dragging&&SystemClock.uptimeMillis()-lastDragHeartbeat>900){lastDragHeartbeat=SystemClock.uptimeMillis();mouse("move",lastX,lastY,0);}
                if (autoClip.isChecked() && hasWindowFocus()) syncClipboard(false);
            }
            ui.postDelayed(this, 180);
        }
    };

    @Override public void onCreate(Bundle saved) {
        super.onCreate(saved);
        getWindow().setStatusBarColor(Color.rgb(15,23,42));
        clipboard = (ClipboardManager)getSystemService(CLIPBOARD_SERVICE);
        root = new LinearLayout(this); root.setOrientation(1);
        root.setPadding(18,24,18,12); root.setBackgroundColor(Color.rgb(245,247,250));
        setContentView(root);
        root.setOnApplyWindowInsetsListener((v, insets) -> {
            root.setPadding(18, Math.max(24,insets.getSystemWindowInsetTop()),18,Math.max(12,insets.getSystemWindowInsetBottom()));
            return insets;
        });
        TextView title = label("近控 · LanRemote",24); root.addView(title);
        root.addView(label("离线局域网 · 无账号 · 加密直连",13));
        status = label("填写电脑窗口中的连接信息",14); root.addView(status);
        login = new LinearLayout(this); login.setOrientation(1); root.addView(login);
        host = input("电脑 IPv4 地址:8765",login);
        fingerprint = input("24 位证书校验码",login);
        pin = input("8 位配对码",login); pin.setInputType(2);
        android.content.SharedPreferences prefs = getPreferences(0);
        host.setText(prefs.getString("host","")); fingerprint.setText(prefs.getString("fingerprint",""));
        button(login,"连接电脑",this::connect);
        login.addView(label("电脑与手机连接同一 Wi-Fi 或热点。连接后需要在电脑窗口点击允许。",14));
        remote = new LinearLayout(this); remote.setOrientation(1);
        root.addView(remote,new LinearLayout.LayoutParams(-1,0,1)); remote.setVisibility(View.GONE);
        touchSlop=ViewConfiguration.get(this).getScaledTouchSlop();
        sensitivity=prefs.getFloat("sensitivity",1.4f);
        touchpad=prefs.getBoolean("touchpad",true);
        screen = new ScreenView(); screen.setScaleType(ImageView.ScaleType.FIT_CENTER); screen.setBackgroundColor(Color.BLACK);
        remote.addView(screen,new LinearLayout.LayoutParams(-1,0,1));
        screen.setOnTouchListener((v,e)->touch(e));
        mouseHint=label("",12);remote.addView(mouseHint);
        LinearLayout row = row(remote);mouseButtons=row;
        button(row,"左键",()->mouse("left",lastX,lastY,0));
        button(row,"右键",()->mouse("right",lastX,lastY,0));
        button(row,"滚↑",()->mouse("scroll",lastX,lastY,1));
        button(row,"滚↓",()->mouse("scroll",lastX,lastY,-1));
        drag = new CheckBox(this); drag.setText("拖拽"); row.addView(drag);
        mouseOptions=row(remote);
        modeButton=new Button(this);modeButton.setTextSize(12);mouseOptions.addView(modeButton);
        modeButton.setOnClickListener(v->{endGesture();touchpad=!touchpad;getPreferences(0).edit().putBoolean("touchpad",touchpad).apply();updateMouseHint();});
        mouseOptions.addView(label("速度",12));
        SeekBar speed=new SeekBar(this);speed.setMax(25);speed.setProgress(Math.round((sensitivity-.5f)*10));
        mouseOptions.addView(speed,new LinearLayout.LayoutParams(0,-2,1));
        speed.setOnSeekBarChangeListener(new SeekBar.OnSeekBarChangeListener(){
            public void onProgressChanged(SeekBar bar,int value,boolean user){sensitivity=.5f+value/10f;}
            public void onStartTrackingTouch(SeekBar bar){}
            public void onStopTrackingTouch(SeekBar bar){getPreferences(0).edit().putFloat("sensitivity",sensitivity).apply();}
        });
        updateMouseHint();
        LinearLayout row2 = row(remote);
        button(row2,"发送文件",()->{ Intent i = new Intent(Intent.ACTION_OPEN_DOCUMENT); i.setType("*/*"); i.addCategory(Intent.CATEGORY_OPENABLE); i.putExtra(Intent.EXTRA_ALLOW_MULTIPLE,true); startActivityForResult(i,1); });
        button(row2,"电脑文件",this::listFiles);
        button(row2,"断开",this::disconnect);
        autoClip = new CheckBox(this); autoClip.setText("前台自动同步文字剪贴板"); remote.addView(autoClip);
        button(remote,"立即同步剪贴板",()->syncClipboard(true));
        pendingLabel = label("",13); root.addView(pendingLabel);
        button(root,"发送待传文件到电脑",this::uploadPending);
        acceptShare(getIntent());
        ui.post(tick);
    }

    TextView label(String text,int size) { TextView v = new TextView(this); v.setText(text); v.setTextSize(size); v.setTextColor(Color.rgb(25,40,58)); v.setPadding(0,5,0,5); return v; }
    EditText input(String hint,LinearLayout parent) { EditText e = new EditText(this); e.setSingleLine(true); e.setHint(hint); e.setTextSize(16); parent.addView(e); return e; }
    LinearLayout row(LinearLayout parent) { LinearLayout r = new LinearLayout(this); parent.addView(r); return r; }
    void button(LinearLayout parent,String text,Runnable action) { Button b = new Button(this); b.setText(text); b.setTextSize(12); b.setMinWidth(0); b.setPadding(10,2,10,2); parent.addView(b); b.setOnClickListener(v->action.run()); }
    void info(String s) { ui.post(()->status.setText(s)); }
    void error(Exception e) { info("操作失败："+(e.getMessage()==null?e.getClass().getSimpleName():e.getMessage())); }

    void connect() {
        if (connected || connecting) return;
        final String h = host.getText().toString().trim();
        final String fp = fingerprint.getText().toString().replaceAll("[\\s:-]", "").toUpperCase(Locale.ROOT);
        final String code = pin.getText().toString().trim();
        if (!h.matches("[0-9.]+:[0-9]{1,5}") || !fp.matches("[A-F0-9]{24}") || !code.matches("[0-9]{8}")) { info("请填写 IPv4:端口、24 位校验码及 8 位配对码"); return; }
        info("正在检查电脑是否可达…");
        connecting=true;
        controls.execute(()->{
            boolean reachable=false;
            try {
                TrustManager[] tm = {new X509TrustManager() {
                    public X509Certificate[] getAcceptedIssuers(){return new X509Certificate[0];}
                    public void checkClientTrusted(X509Certificate[] c,String a) throws java.security.cert.CertificateException {throw new java.security.cert.CertificateException("client cert unsupported");}
                    public void checkServerTrusted(X509Certificate[] chain,String auth) throws java.security.cert.CertificateException {
                        try {
                            byte[] digest=MessageDigest.getInstance("SHA-256").digest(chain[0].getEncoded());
                            StringBuilder hex=new StringBuilder(); for(byte b:digest) hex.append(String.format(Locale.ROOT,"%02X",b));
                            if(!MessageDigest.isEqual(hex.substring(0,24).getBytes("UTF-8"),fp.getBytes("UTF-8"))) throw new GeneralSecurityException("证书校验码不匹配");
                        } catch(Exception e){throw new java.security.cert.CertificateException(e);}
                    }
                }};
                SSLContext ctx = SSLContext.getInstance("TLS"); ctx.init(null,tm,new SecureRandom());
                tls = ctx.getSocketFactory(); address="https://"+h;
                JSONObject hello=json("/hello",null);
                if(!"LanRemote".equals(hello.optString("product")))throw new IOException("该地址不是近控电脑端");
                if(!hello.optBoolean("cursor"))throw new IOException("虚拟鼠标需要电脑端 0.2.0，请同时更新电脑 EXE");
                reachable=true;
                info("已连通电脑，正在请求配对；请留意电脑弹窗…");
                String t=json("/pair",new JSONObject().put("pin",code)).getString("token");
                if(t.equals("null")||t.isEmpty()) throw new IOException("配对被拒绝");
                token=t;
                JSONObject initialCursor=json("/cursor",null);
                connected=true; lastClip=null;
                ui.post(()->{
                    pointer.set((float)initialCursor.optDouble("x",.5),(float)initialCursor.optDouble("y",.5));showPointer();
                    getPreferences(0).edit().putString("host",h).putString("fingerprint",fp).apply();
                    login.setVisibility(View.GONE); remote.setVisibility(View.VISIBLE);
                    adaptLayout();
                    lastInput=0;
                    status.setText("已连接 · 画面仅在前台刷新");
                });
            }catch(Exception e){
                if(e instanceof SocketTimeoutException || e instanceof ConnectException || e instanceof NoRouteToHostException){
                    info(reachable?"电脑已连通，但配对未完成。请查看电脑配对弹窗及日志后重试。":"尚未连通电脑。请检查 Wi-Fi 地址、同一局域网和防火墙 TCP 8765；此时电脑不会弹窗。");
                }else if(e instanceof SSLException){
                    info("加密连接校验失败，请核对电脑显示的 24 位证书校验码。详情："+e.getMessage());
                }else{error(e);}
            }finally{connecting=false;}
        });
    }

    HttpsURLConnection open(String path,String method) throws Exception {
        HttpsURLConnection c=(HttpsURLConnection)new URL(address+path).openConnection();
        c.setSSLSocketFactory(tls);
        // Identity is explicitly pinned above; no public DNS name is involved on a private LAN.
        c.setHostnameVerifier((hostname,session)->true);
        c.setConnectTimeout(7000); c.setReadTimeout(path.equals("/pair")?30000:15000);
        c.setInstanceFollowRedirects(false); c.setRequestMethod(method);
        if(!token.isEmpty()) c.setRequestProperty("Authorization","Bearer "+token);
        return c;
    }
    byte[] read(InputStream in,int max) throws IOException {
        ByteArrayOutputStream out=new ByteArrayOutputStream(); byte[] buf=new byte[16384]; int n;
        while((n=in.read(buf))!=-1){if(out.size()+n>max)throw new IOException("响应过大");out.write(buf,0,n);} return out.toByteArray();
    }
    InputStream checked(HttpsURLConnection c) throws Exception {
        int code=c.getResponseCode();
        if(code!=200&&"/hello".equals(c.getURL().getPath()))throw new IOException("请将电脑端也更新到 0.1.1 或更新版本（HTTP "+code+"）");
        if(code!=200){if(code==401)ui.post(this::disconnect);throw new IOException(code==403?"配对码错误、被拒绝或尝试过多，请稍后重试":"电脑返回 HTTP "+code);}
        return c.getInputStream();
    }
    byte[] request(String path,JSONObject payload,int max) throws Exception {
        HttpsURLConnection c=open(path,payload==null?"GET":"POST");
        try {
            if(payload!=null){byte[] b=payload.toString().getBytes("UTF-8");c.setDoOutput(true);c.setFixedLengthStreamingMode(b.length);c.setRequestProperty("Content-Type","application/json");try(OutputStream out=c.getOutputStream()){out.write(b);}}
            try(InputStream in=checked(c)){return read(in,max);}
        }finally{c.disconnect();}
    }
    JSONObject json(String path,JSONObject payload) throws Exception {return new JSONObject(new String(request(path,payload,1024*1024),"UTF-8"));}
    void disconnect(){
        endGesture();
        latestMove.set(null);
        final String previous=token;
        if(connected) controls.execute(()->{
            try{HttpsURLConnection c=open("/disconnect","POST");try{c.setRequestProperty("Authorization","Bearer "+previous);c.setDoOutput(true);c.setFixedLengthStreamingMode(0);c.getOutputStream().close();c.getResponseCode();}finally{c.disconnect();}}catch(Exception ignored){}
        });
        connected=false; token=""; lastClip=null;
        adaptLayout();screen.setImageDrawable(null);info("已断开");
    }
    void refreshFrame(){
        if(frameBusy)return; frameBusy=true;
        final long inputVersion=lastInput;
        final boolean pollCursor=!fingerDown&&!dragging&&!movePending.get()&&SystemClock.uptimeMillis()-lastInput>600&&SystemClock.uptimeMillis()-lastCursorPoll>500;
        if(pollCursor)lastCursorPoll=SystemClock.uptimeMillis();
        frames.execute(()->{try{
            byte[] data=request("/screen",null,8*1024*1024);Bitmap bm=BitmapFactory.decodeByteArray(data,0,data.length);if(bm==null)throw new IOException("无法解码画面");
            JSONObject position=pollCursor?json("/cursor",null):null;
            ui.post(()->{if(connected&&foreground){screen.setImageBitmap(bm);if(position!=null&&lastInput==inputVersion&&!fingerDown&&!dragging&&!movePending.get()){pointer.set((float)position.optDouble("x",.5),(float)position.optDouble("y",.5));showPointer();}}});
        }catch(Exception e){error(e);}finally{frameBusy=false;}});
    }
    void updateMouseHint(){
        modeButton.setText(touchpad?"触摸板 ▾":"点按 ▾");
        mouseHint.setText(touchpad?"滑动移动光标 · 轻点左键/连点双击 · 长按拖拽 · 双指滚动":"点按定位点击 · 长按或勾选拖拽后移动 · 双指滚动");
    }
    void showPointer(){lastX=pointer.x;lastY=pointer.y;screen.invalidate();}
    void beginDrag(){if(fingerDown&&!gestureMoved&&!multiTouch){dragging=true;mouse("down",lastX,lastY,0);screen.invalidate();}}
    void endGesture(){
        ui.removeCallbacks(longPress);
        if(dragging)mouse("up",lastX,lastY,0);
        fingerDown=false;dragging=false;multiTouch=false;
    }
    class ScreenView extends ImageView {
        final Paint paint=new Paint(Paint.ANTI_ALIAS_FLAG);
        ScreenView(){super(MainActivity.this);}
        RectF imageBounds(){
            if(getDrawable()==null)return new RectF();
            float iw=getDrawable().getIntrinsicWidth(),ih=getDrawable().getIntrinsicHeight();
            float scale=Math.min(getWidth()/iw,getHeight()/ih);
            return new RectF((getWidth()-iw*scale)/2,(getHeight()-ih*scale)/2,(getWidth()+iw*scale)/2,(getHeight()+ih*scale)/2);
        }
        @Override protected void onDraw(Canvas canvas){
            super.onDraw(canvas);
            if(getDrawable()==null)return;
            RectF r=imageBounds();float x=r.left+lastX*r.width(),y=r.top+lastY*r.height();
            float unit=getResources().getDisplayMetrics().density;
            canvas.save();canvas.clipRect(r);canvas.translate(x,y);canvas.scale(unit,unit);
            Path arrow=new Path();arrow.moveTo(0,0);arrow.lineTo(2,19);arrow.lineTo(6,14);arrow.lineTo(10,22);arrow.lineTo(14,20);arrow.lineTo(10,12);arrow.lineTo(17,12);arrow.close();
            paint.setStyle(Paint.Style.FILL);paint.setColor(dragging?Color.rgb(245,158,11):Color.rgb(56,189,248));canvas.drawPath(arrow,paint);
            paint.setStyle(Paint.Style.STROKE);paint.setStrokeWidth(1.5f);paint.setColor(Color.BLACK);canvas.drawPath(arrow,paint);canvas.restore();
        }
    }
    boolean touch(MotionEvent e){
        if(screen.getDrawable()==null)return true;
        RectF r=screen.imageBounds();
        int action=e.getActionMasked();
        lastInput=SystemClock.uptimeMillis();
        if(action==MotionEvent.ACTION_CANCEL){endGesture();return true;}
        if(action==MotionEvent.ACTION_DOWN){
            endGesture();fingerDown=true;gestureMoved=false;multiTouch=false;touchStarted=lastInput;
            previousX=startX=e.getX();previousY=startY=e.getY();
            if(!touchpad){if(!r.contains(startX,startY)){fingerDown=false;return true;}pointer.set((startX-r.left)/r.width(),(startY-r.top)/r.height());showPointer();mouse("move",lastX,lastY,0);}
            if(drag.isChecked()){dragging=true;mouse("down",lastX,lastY,0);}else ui.postDelayed(longPress,500);
        }else if(action==MotionEvent.ACTION_POINTER_DOWN){
            ui.removeCallbacks(longPress);if(dragging)mouse("up",lastX,lastY,0);dragging=false;multiTouch=true;gestureMoved=true;
            scrollY=(e.getY(0)+e.getY(1))/2;scrollRemainder=0;
        }else if(action==MotionEvent.ACTION_MOVE&&fingerDown){
            if(multiTouch){
                if(e.getPointerCount()>=2){float cy=(e.getY(0)+e.getY(1))/2;scrollRemainder+=cy-scrollY;scrollY=cy;
                    float step=30*getResources().getDisplayMetrics().density;int ticks=(int)(scrollRemainder/step);
                    if(ticks!=0){mouse("scroll",lastX,lastY,Math.max(-5,Math.min(5,ticks)));scrollRemainder-=ticks*step;}}
                return true;
            }
            float dx=e.getX()-previousX,dy=e.getY()-previousY;
            if(Math.hypot(e.getX()-startX,e.getY()-startY)>touchSlop){gestureMoved=true;ui.removeCallbacks(longPress);}
            if(touchpad)pointer.move(dx,dy,r.width(),r.height(),sensitivity);
            else pointer.set((e.getX()-r.left)/r.width(),(e.getY()-r.top)/r.height());
            previousX=e.getX();previousY=e.getY();showPointer();mouse("move",lastX,lastY,0);
        }else if(action==MotionEvent.ACTION_UP){
            if(fingerDown&&!multiTouch&&!gestureMoved&&!dragging&&lastInput-touchStarted<500)mouse("left",lastX,lastY,0);
            endGesture();screen.invalidate();
        }
        return true;
    }
    void scheduleMove(){
        if(!connected||!movePending.compareAndSet(false,true))return;
        controls.execute(()->{
            try{float[] p=latestMove.getAndSet(null);if(p!=null&&connected)json("/mouse",new JSONObject().put("action","move").put("x",p[0]).put("y",p[1]));}
            catch(Exception e){error(e);}finally{movePending.set(false);if(latestMove.get()!=null&&connected)scheduleMove();}
        });
    }
    void mouse(String action,float x,float y,int delta){
        if(!connected)return;
        lastInput=SystemClock.uptimeMillis();
        if(action.equals("move")){latestMove.set(new float[]{x,y});scheduleMove();return;}
        latestMove.set(null);
        controls.execute(()->{try{
            if(action.equals("scroll"))json("/mouse",new JSONObject().put("action","move").put("x",x).put("y",y));
            json("/mouse",new JSONObject().put("action",action).put("x",x).put("y",y).put("delta",delta));
        }catch(Exception e){error(e);}});
    }
    long lastClipCheck;
    void syncClipboard(boolean force){
        if(!connected||clipBusy||!hasWindowFocus())return;
        if(!force&&SystemClock.uptimeMillis()-lastClipCheck<1500)return;
        lastClipCheck=SystemClock.uptimeMillis();
        ClipData clip=clipboard.getPrimaryClip();
        String local=clip!=null&&clip.getItemCount()>0&&clip.getItemAt(0).getText()!=null?clip.getItemAt(0).getText().toString():"";
        if(local.length()>100000){info("剪贴板文字最多 10 万字符");return;}
        boolean push=!local.isEmpty()&&!local.equals(lastClip);
        clipBusy=true;
        controls.execute(()->{
            try{
                String text=json("/clipboard",push?new JSONObject().put("text",local):null).getString("text");
                ui.post(()->{
                    if(!connected||!hasWindowFocus())return;
                    // Do not overwrite a local copy made while the request was in flight.
                    ClipData current=clipboard.getPrimaryClip();
                    String now=current!=null&&current.getItemCount()>0&&current.getItemAt(0).getText()!=null?current.getItemAt(0).getText().toString():"";
                    if(!now.equals(local))return;
                    if(!text.equals(local))clipboard.setPrimaryClip(ClipData.newPlainText("近控",text));
                    lastClip=text;
                    if(force)info("文字剪贴板已同步");
                });
            }catch(Exception e){error(e);}finally{clipBusy=false;}
        });
    }
    @Override protected void onNewIntent(Intent intent){super.onNewIntent(intent);setIntent(intent);acceptShare(intent);}
    void acceptShare(Intent intent){
        if(intent==null)return;
        String a=intent.getAction();
        if(Intent.ACTION_SEND.equals(a)){
            Uri uri=intent.getParcelableExtra(Intent.EXTRA_STREAM);addUri(uri);
        }else if(Intent.ACTION_SEND_MULTIPLE.equals(a)){
            ArrayList<Uri> list=intent.getParcelableArrayListExtra(Intent.EXTRA_STREAM);if(list!=null)for(Uri u:list)addUri(u);
        }else if(Intent.ACTION_VIEW.equals(a))addUri(intent.getData());
        pendingLabel.setText("待发送："+pending.size()+" 个文件");
    }
    void addUri(Uri uri){if(uri!=null&&"content".equals(uri.getScheme())&&!pending.contains(uri))pending.add(uri);}
    String displayName(Uri uri){
        try(Cursor c=getContentResolver().query(uri,new String[]{OpenableColumns.DISPLAY_NAME},null,null,null)){if(c!=null&&c.moveToFirst())return c.getString(0);}catch(Exception ignored){}
        return "file.bin";
    }
    void uploadPending(){
        if(!connected){info("请先连接电脑，待传文件会暂时保留");return;}
        if(transferring){info("正在传输，请等待");return;}
        if(pending.isEmpty()){info("请通过发送文件或微信的其他应用入口选择文件");return;}
        final ArrayList<Uri> batch=new ArrayList<>(pending);transferring=true;
        files.execute(()->{
            try{
                for(Uri uri:batch){
                    String name=displayName(uri);info("准备发送："+name);
                    File temp=File.createTempFile("upload-",".tmp",getCacheDir());
                    try{
                        // Content providers may not expose a length. Spool once to support bounded streaming.
                        try(InputStream in=getContentResolver().openInputStream(uri);OutputStream out=new FileOutputStream(temp)){if(in==null)throw new IOException("无法读取分享文件");copy(in,out,2L*1024*1024*1024);}
                        HttpsURLConnection c=open("/upload?name="+URLEncoder.encode(name,"UTF-8"),"POST");
                        try{
                            c.setDoOutput(true);c.setFixedLengthStreamingMode(temp.length());c.setReadTimeout(30000);
                            info("正在发送："+name);
                            try(InputStream in=new FileInputStream(temp);OutputStream out=c.getOutputStream()){copy(in,out,2L*1024*1024*1024);}
                            try(InputStream in=checked(c)){read(in,65536);}
                        }finally{c.disconnect();}
                        ui.post(()->{pending.remove(uri);pendingLabel.setText("待发送："+pending.size()+" 个文件");});
                    }finally{temp.delete();}
                }
                info("文件已传到电脑");
            }catch(Exception e){error(e);}finally{transferring=false;}
        });
    }
    long copy(InputStream in,OutputStream out,long max) throws IOException {
        byte[] buf=new byte[65536];long count=0;int n;
        while((n=in.read(buf))!=-1){if(!connected)throw new IOException("连接已断开");count+=n;if(count>max)throw new IOException("单个文件最大 2 GB");out.write(buf,0,n);}
        return count;
    }
    void listFiles(){
        files.execute(()->{try{
            JSONArray list=new JSONArray(new String(request("/files",null,1024*1024),"UTF-8"));
            String[] names=new String[list.length()];for(int i=0;i<names.length;i++)names[i]=list.getJSONObject(i).getString("name");
            ui.post(()->{
                if(names.length==0){info("先在电脑端点击“选择文件发给手机”");return;}
                new AlertDialog.Builder(this).setTitle("下载电脑分享的文件").setItems(names,(d,index)->{
                    try{downloadId=list.getJSONObject(index).getString("id");Intent intent=new Intent(Intent.ACTION_CREATE_DOCUMENT);intent.setType("application/octet-stream");intent.addCategory(Intent.CATEGORY_OPENABLE);intent.putExtra(Intent.EXTRA_TITLE,names[index]);startActivityForResult(intent,2);}catch(Exception e){error(e);}
                }).show();
            });
        }catch(Exception e){error(e);}});
    }
    @Override protected void onActivityResult(int requestCode,int resultCode,Intent data){
        super.onActivityResult(requestCode,resultCode,data);
        if(resultCode!=RESULT_OK||data==null)return;
        if(requestCode==1){if(data.getClipData()!=null){for(int i=0;i<data.getClipData().getItemCount();i++)addUri(data.getClipData().getItemAt(i).getUri());}else addUri(data.getData());pendingLabel.setText("待发送："+pending.size()+" 个文件");uploadPending();}
        if(requestCode==2&&downloadId!=null&&data.getData()!=null){
            final String id=downloadId;final Uri dest=data.getData();
            files.execute(()->{
                try{
                    HttpsURLConnection c=open("/download?id="+id,"GET");
                    try(InputStream in=checked(c);OutputStream out=getContentResolver().openOutputStream(dest)){
                        if(out==null)throw new IOException("不能写入目标文件");info("正在下载…");long actual=copy(in,out,Long.MAX_VALUE);
                        if(c.getContentLengthLong()>=0&&actual!=c.getContentLengthLong())throw new IOException("下载中断，文件不完整");
                    }finally{c.disconnect();}
                    info("文件已保存到选择的位置");
                }catch(Exception e){try{android.provider.DocumentsContract.deleteDocument(getContentResolver(),dest);}catch(Exception ignored){}error(e);}
            });
        }
    }
    @Override protected void onResume(){super.onResume();foreground=true;}
    void adaptLayout(){
        boolean wide=connected&&getResources().getConfiguration().orientation==android.content.res.Configuration.ORIENTATION_LANDSCAPE;
        for(int i=0;i<root.getChildCount();i++){View v=root.getChildAt(i);v.setVisibility(wide&&v!=remote?View.GONE:View.VISIBLE);}
        login.setVisibility(connected?View.GONE:View.VISIBLE);remote.setVisibility(connected?View.VISIBLE:View.GONE);
        for(int i=0;i<remote.getChildCount();i++){View v=remote.getChildAt(i);v.setVisibility(wide&&v!=screen&&v!=mouseButtons&&v!=mouseOptions?View.GONE:View.VISIBLE);}
    }
    @Override public void onConfigurationChanged(android.content.res.Configuration config){endGesture();super.onConfigurationChanged(config);adaptLayout();}
    @Override protected void onPause(){endGesture();foreground=false;if(connected)mouse("up",lastX,lastY,0);super.onPause();}
    @Override protected void onDestroy(){endGesture();connected=false;ui.removeCallbacks(tick);controls.shutdownNow();frames.shutdownNow();files.shutdownNow();super.onDestroy();}
}
