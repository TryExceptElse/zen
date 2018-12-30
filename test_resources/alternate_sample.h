#include <vector>

namespace sample {


/**
 * *Changed* class declaration
 */
class Foo {
 public:
  explicit Foo(/*test*/std::vector<int> numbers): numbers_(numbers) {}

  void Print() const;

  // Added whitespace

 private:
  std::vector<int> numbers_;
};


}  // namespace sample
