package water.api;

import hex.Model;
import water.Job;
import water.Key;
import water.Keyed;
import water.fvec.Frame;

public class KeyV1<T extends Keyed> extends KeySchema<T> {
  public KeyV1() {}
  public KeyV1(Key<T> key) {
    super(key);
  }

  public static class JobKeyV1 extends KeySchema<Job> {
    public JobKeyV1() {}
    public JobKeyV1(Key<Job> key) {
      super(key);
    }
  }

  public static class FrameKeyV1 extends KeySchema<Frame> {
    public FrameKeyV1() {}
    public FrameKeyV1(Key<Frame> key) {
      super(key);
    }
  }

  public static class ModelKeyV1 extends KeySchema<Model> {
    public ModelKeyV1() {}
    public ModelKeyV1(Key<Model> key) {
      super(key);
    }
  }
}
