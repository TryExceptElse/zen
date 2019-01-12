#include <vector>

namespace sample {


/**
 * Sample class declaration
 */
class Foo {
 public:
  explicit Foo(std::vector<int> numbers): numbers_(numbers) {}

  void Print() const;

  /** New numbers accessor */
  const std::vector<int> numbers() const { return numbers_; }
 private:
  std::vector<int> numbers_;
};


}  // namespace sample
