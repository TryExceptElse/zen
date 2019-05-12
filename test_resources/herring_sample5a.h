#include <vector>
#include <string>

namespace sample {


/**
 * Sample class declaration
 */
class Foo {
 public:
  explicit Foo(/*test*/std::vector<int> numbers): numbers_(numbers) {}

  void Print() const;

  std::string get_shrubbery() const { return "It is a good shrubbery."; }

 private:
  std::vector<int> numbers_;
};

}  // namespace sample
