import jakarta.servlet.http.HttpServlet;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import java.io.IOException;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.file.Files;
import org.apache.catalina.Context;
import org.apache.catalina.startup.Tomcat;

// A loopback-only servlet and a fixed chat-completions response for the cookbook.
public class ReturnsServlet {
    public static void main(String[] args) throws Exception {
        var tomcat = new Tomcat();
        tomcat.setBaseDir(Files.createTempDirectory("ridgeline-tomcat").toString());
        tomcat.setPort(5101);
        tomcat.getConnector().setProperty("address", "127.0.0.1");
        Context app = tomcat.addContext("", Files.createTempDirectory("ridgeline-web").toString());
        var client = HttpClient.newHttpClient();

        Tomcat.addServlet(app, "policy", new HttpServlet() {
            @Override protected void doGet(HttpServletRequest req, HttpServletResponse res) throws IOException {
                var query = HttpRequest.newBuilder(URI.create("http://127.0.0.1:5101/v1/chat/completions"))
                    .header("Content-Type", "application/json")
                    .POST(HttpRequest.BodyPublishers.ofString("""
                        {"model":"returns-fixture","messages":[{"role":"user","content":"Can I return an unused tent?"}]}
                        """)).build();
                try {
                    var reply = client.send(query, HttpResponse.BodyHandlers.ofString());
                    res.setStatus(reply.statusCode());
                    res.setContentType("text/plain");
                    res.getWriter().println("Servlet received: " + req.getHeader("traceparent"));
                    res.getWriter().println(reply.body());
                } catch (InterruptedException err) {
                    Thread.currentThread().interrupt();
                    res.sendError(503);
                }
            }
        });
        app.addServletMappingDecoded("/return-policy", "policy");

        Tomcat.addServlet(app, "model", new HttpServlet() {
            @Override protected void doPost(HttpServletRequest req, HttpServletResponse res) throws IOException {
                req.getInputStream().readAllBytes();
                res.setContentType("application/json");
                res.getWriter().print("""
                    {"id":"ridgeline-demo","object":"chat.completion","model":"returns-fixture","choices":[{"index":0,"message":{"role":"assistant","content":"Yes, within 30 days."},"finish_reason":"stop"}]}
                    """);
            }
        });
        app.addServletMappingDecoded("/v1/chat/completions", "model");
        tomcat.start();
        tomcat.getServer().await();
    }
}
