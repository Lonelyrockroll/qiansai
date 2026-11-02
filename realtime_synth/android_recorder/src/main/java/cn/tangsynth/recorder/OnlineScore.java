package cn.tangsynth.recorder;

import java.io.*;
import java.net.*;
import java.util.Locale;

/** Downloads one user-selected file into staging. The importer validates it before replacement. */
final class OnlineScore {
    enum Kind {
        PDF("PDF",20*1024*1024,"%PDF-"), MIDI("MIDI",MidiGuide.MAX_BYTES,"MThd");
        final String label, signature; final int limit;
        Kind(String label,int limit,String signature){this.label=label;this.limit=limit;this.signature=signature;}
    }
    static final String EXAMPLE_BASE="https://www.mutopiaproject.org/ftp/HoretzkyF/horetzky25/horetzky25";
    static String example(Kind kind){return EXAMPLE_BASE+(kind==Kind.PDF?"-a4.pdf":".mid");}
    interface Importer { void importFile(File file,String displayName)throws IOException; }
    interface Connections { HttpURLConnection open(URL url)throws IOException; }

    static URL validate(String text)throws IOException {
        if(text==null || text.trim().length()>4096)throw new IOException("链接过长或为空");
        try {
            URI uri=new URI(text.trim());
            if(!"https".equalsIgnoreCase(uri.getScheme()) || uri.getHost()==null || uri.getRawUserInfo()!=null)
                throw new IOException("请输入 HTTPS 文件直链，链接中不要包含账号或密码");
            return uri.toURL();
        } catch(URISyntaxException|IllegalArgumentException ex){throw new IOException("链接格式有误，请重新复制文件直链",ex);}
    }
    static void fetch(String link,Kind kind,File directory,Importer importer)throws IOException {
        fetch(link,kind,directory,importer,url->(HttpURLConnection)url.openConnection());
    }
    static void fetch(String link,Kind kind,File directory,Importer importer,Connections connections)throws IOException {
        URL url=validate(link);
        long deadline=System.nanoTime()+60_000_000_000L;
        for(int redirects=0;;redirects++){
            checkDeadline(deadline);
            HttpURLConnection conn=connections.open(url);
            try {
                conn.setInstanceFollowRedirects(false);conn.setUseCaches(false);
                conn.setConnectTimeout(10000);conn.setReadTimeout(12000);
                conn.setRequestProperty("User-Agent","TangMusic/1.3");
                conn.setRequestProperty("Accept-Encoding","identity");
                int status=conn.getResponseCode();
                if(status==301 || status==302 || status==303 || status==307 || status==308){
                    String location=conn.getHeaderField("Location");
                    if(redirects>=3 || location==null || location.trim().isEmpty())throw new IOException("服务器跳转异常，请使用最终文件直链");
                    url=validate(new URL(url,location).toExternalForm());continue;
                }
                if(status!=HttpURLConnection.HTTP_OK)throw new IOException("服务器返回 HTTP "+status+"，请检查曲谱链接");
                long declared=declaredLength(conn);
                if(declared>kind.limit)throw sizeError(kind);
                File candidate=File.createTempFile("online-",".tmp",directory);
                try {
                    int count=0; byte[] block=new byte[8192];
                    try(InputStream in=conn.getInputStream();OutputStream out=new FileOutputStream(candidate)){
                        for(int n;(n=in.read(block))!=-1;){
                            checkDeadline(deadline);
                            if(n>kind.limit-count)throw sizeError(kind);
                            out.write(block,0,n);count+=n;
                        }
                    }
                    if(declared>=0 && declared!=count)throw new IOException("文件接收不完整，请重新下载");
                    try(InputStream in=new FileInputStream(candidate)){
                        for(char c:kind.signature.toCharArray())if(in.read()!=c)
                            throw new IOException("没有收到有效的 "+kind.label+" 文件，请使用文件直链");
                    }
                    String path=url.toURI().getPath();String title=path.substring(path.lastIndexOf('/')+1);
                    title=title.replaceAll("[\\p{Cntrl}]"," ").trim();
                    if(title.isEmpty())title="在线 "+kind.label;
                    checkDeadline(deadline);
                    importer.importFile(candidate,title.substring(0,Math.min(120,title.length())));
                } catch(URISyntaxException ex){throw new IOException("曲谱链接无效",ex);}
                finally{candidate.delete();}
                return;
            } catch(SocketTimeoutException ex){throw new IOException("网络连接超时，请再次下载",ex);}
            finally{conn.disconnect();}
        }
    }
    private static long declaredLength(HttpURLConnection connection)throws IOException {
        String value=connection.getHeaderField("Content-Length");if(value==null)return -1;
        try{long size=Long.parseLong(value);if(size<0)throw new NumberFormatException();return size;}
        catch(NumberFormatException e){throw new IOException("服务器返回的文件长度无效",e);}
    }
    private static void checkDeadline(long deadline)throws IOException {
        if(Thread.currentThread().isInterrupted())throw new InterruptedIOException("下载已取消");
        if(System.nanoTime()-deadline>=0)throw new SocketTimeoutException("下载超过一分钟，请重试");
    }
    private static IOException sizeError(Kind kind){return new IOException(String.format(Locale.CHINA,"%s 超过 %d MB 上限",kind.label,kind.limit/(1024*1024)));}
}
