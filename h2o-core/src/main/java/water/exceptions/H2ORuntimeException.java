package water.exceptions;

import org.jboss.netty.handler.codec.http.HttpResponseStatus;
import water.H2OError;
import water.util.IcedHashMap;

/**
 * RuntimeException which results in an http 400 error, and serves as a base class for other error types.
 */
public class H2ORuntimeException extends RuntimeException {
  protected int HTTP_RESPONSE_CODE() { return HttpResponseStatus.BAD_REQUEST.getCode(); }

  public long timestamp;
  public String dev_message;
  public IcedHashMap<String, Object> values;

  public H2ORuntimeException(String message, String dev_message, IcedHashMap values) {
    super(message);

    this.timestamp = System.currentTimeMillis();
    this.dev_message = dev_message;
    this.values = values;
  }

  public H2ORuntimeException(String msg, String dev_msg) {
    this(msg, dev_msg, new IcedHashMap());
  }

  public H2OError toH2OError() {
    return new H2OError(timestamp, null, getMessage(), dev_message, HTTP_RESPONSE_CODE(), values, this);
  }

  public H2OError toH2OError(String error_url) {
    return new H2OError(timestamp, error_url, getMessage(), dev_message, HTTP_RESPONSE_CODE(), values, this);
  }
}
