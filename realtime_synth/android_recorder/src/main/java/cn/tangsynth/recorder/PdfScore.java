package cn.tangsynth.recorder;

import android.graphics.Bitmap;
import android.graphics.Color;
import android.graphics.Matrix;
import android.graphics.pdf.PdfRenderer;
import android.os.ParcelFileDescriptor;
import java.io.*;

/** Android owns PDF parsing; the board receives only one already-rendered black/white page. */
final class PdfScore {
    static final int MAX_FILE_BYTES=20*1024*1024,MAX_PAGES=200;
    static final class Rendered {
        final ScoreProtocol.Page page;final Bitmap preview;
        Rendered(ScoreProtocol.Page page,Bitmap preview){this.page=page;this.preview=preview;}
    }
    static void copy(InputStream in,File destination)throws IOException{
        try(OutputStream out=new FileOutputStream(destination)){
            byte[] buffer=new byte[32768];int total=0,n;
            while((n=in.read(buffer))!=-1){total+=n;if(total>MAX_FILE_BYTES)throw new IOException("PDF 超过 20 MB，请先压缩或选取需要的页面");out.write(buffer,0,n);}
            if(total==0)throw new IOException("PDF 文件为空");
        }
    }
    static Rendered render(File file,int index)throws IOException{
        Bitmap bitmap=null;
        try(ParcelFileDescriptor descriptor=ParcelFileDescriptor.open(file,ParcelFileDescriptor.MODE_READ_ONLY);
            PdfRenderer renderer=new PdfRenderer(descriptor)){
            int count=renderer.getPageCount();
            if(count<1 || count>MAX_PAGES)throw new IOException("首版支持 1～200 页 PDF，请先拆分这份曲谱");
            if(index<0 || index>=count)throw new IOException("已经到达曲谱的第一页或最后一页");
            try(PdfRenderer.Page page=renderer.openPage(index)){
                bitmap=Bitmap.createBitmap(ScoreProtocol.WIDTH,ScoreProtocol.HEIGHT,Bitmap.Config.ARGB_8888);bitmap.eraseColor(Color.WHITE);
                float scale=Math.min(1024f/page.getWidth(),600f/page.getHeight());
                float ratio=512f/600f,left=(1024f-page.getWidth()*scale)/2f,top=(600f-page.getHeight()*scale)/2f;
                Matrix matrix=new Matrix();matrix.setValues(new float[]{scale,0,left,0,scale*ratio,top*ratio,0,0,1});
                page.render(bitmap,null,matrix,PdfRenderer.Page.RENDER_MODE_FOR_DISPLAY);
                int[] pixels=new int[ScoreProtocol.WIDTH*ScoreProtocol.HEIGHT];bitmap.getPixels(pixels,0,ScoreProtocol.WIDTH,0,0,ScoreProtocol.WIDTH,ScoreProtocol.HEIGHT);
                byte[] raw=ScoreProtocol.monochrome(pixels);
                for(int i=0;i<pixels.length;i++)pixels[i]=(raw[i>>3]&(128>>(i&7)))!=0?Color.BLACK:Color.WHITE;
                bitmap.setPixels(pixels,0,ScoreProtocol.WIDTH,0,0,ScoreProtocol.WIDTH,ScoreProtocol.HEIGHT);
                Bitmap preview=Bitmap.createScaledBitmap(bitmap,1024,600,false);
                return new Rendered(new ScoreProtocol.Page(raw,index,count),preview);
            }
        }catch(SecurityException ex){throw new IOException("这份 PDF 需要密码，请先另存为不加密的 PDF",ex);}
        catch(IllegalArgumentException|IllegalStateException ex){throw new IOException("无法读取这份 PDF，请检查文件或重新导出",ex);}
        finally{if(bitmap!=null)bitmap.recycle();}
    }
}
